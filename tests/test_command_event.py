"""Isolated tests of the actual command-event dispatcher; no live game is started."""
import unittest
from java_harness import ROOT, run_java

STUBS = {
'carpet/CarpetServer.java': '''package carpet;
import carpet.script.CarpetScriptServer;
public class CarpetServer { public static CarpetScriptServer scriptServer; }
''',
'carpet/CarpetSettings.java': '''package carpet;
public class CarpetSettings { public static int runPermissionLevel = 2; }
''',
'net/minecraft/server/command/ServerCommandSource.java': '''package net.minecraft.server.command;
public class ServerCommandSource {
    public final String name; public final int level;
    public ServerCommandSource(String name, int level) { this.name=name; this.level=level; }
    public String getName() { return name; }
    public ServerCommandSource withLevel(int level) { return new ServerCommandSource(name, level); }
}
''',
'net/minecraft/server/network/ServerPlayerEntity.java': '''package net.minecraft.server.network;
import net.minecraft.server.command.ServerCommandSource;
public class ServerPlayerEntity {
    public final String name;
    public ServerPlayerEntity(String name) { this.name=name; }
    public String getEntityName() { return name; }
    public ServerCommandSource getCommandSource() { return new ServerCommandSource(name, 0); }
}
''',
'net/minecraft/util/math/BlockPos.java': '''package net.minecraft.util.math;
public class BlockPos { public static final BlockPos ORIGIN = new BlockPos(); }
''',
'carpet/script/value/Value.java': '''package carpet.script.value;
public class Value {
    public static final Value NULL = new Value("null"), TRUE = new Value("true"), FALSE = new Value("false");
    private final String value;
    public Value(String value) { this.value=value; }
    public String getString() { return value; }
}
''',
'carpet/script/value/StringValue.java': '''package carpet.script.value;
public class StringValue extends Value { public StringValue(String value) { super(value); } }
''',
'carpet/script/value/EntityValue.java': '''package carpet.script.value;
import net.minecraft.server.network.ServerPlayerEntity;
public class EntityValue extends Value {
    public final ServerPlayerEntity entity;
    public EntityValue(ServerPlayerEntity entity) { super(entity.name); this.entity=entity; }
}
''',
'carpet/script/value/FunctionValue.java': '''package carpet.script.value;
import java.util.List;
import carpet.script.CarpetScriptHost;
import net.minecraft.server.command.ServerCommandSource;
public class FunctionValue {
    public interface Body { Value call(CarpetScriptHost host, ServerCommandSource source, List<Value> args); }
    public final int arity; public final Body body;
    public FunctionValue(int arity, Body body) { this.arity=arity; this.body=body; }
}
''',
'carpet/script/CarpetScriptHost.java': '''package carpet.script;
import java.util.*;
import carpet.CarpetServer;
import carpet.script.exception.InvalidCallbackException;
import carpet.script.value.*;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.util.math.BlockPos;
public class CarpetScriptHost {
    private final boolean perUser;
    public final Map<String, CarpetScriptHost> children = new HashMap<>();
    public int calls;
    public CarpetScriptHost(boolean perUser) { this.perUser=perUser; }
    public boolean isPerUser() { return perUser; }
    public List<CarpetScriptHost> retrieveForExecution(ServerCommandSource source, String target) {
        if (!perUser) return Collections.singletonList(this);
        if (target == null) return new ArrayList<>(children.values());
        CarpetScriptHost child=children.get(target);
        return child == null ? Collections.emptyList() : Collections.singletonList(child);
    }
    public Value callUDF(BlockPos pos, ServerCommandSource source, FunctionValue function, List<Value> args) throws InvalidCallbackException {
        if (CarpetServer.scriptServer.stopAll) return Value.NULL;
        if (function.arity != args.size()) throw new InvalidCallbackException();
        calls++;
        return function.body.call(this, source, args);
    }
}
''',
'carpet/script/CarpetScriptServer.java': '''package carpet.script;
import java.util.*;
public class CarpetScriptServer {
    public boolean stopAll;
    public CarpetScriptHost globalHost = new CarpetScriptHost(false);
    public Map<String, CarpetScriptHost> modules = new HashMap<>();
}
''',
'carpet/script/CarpetEventServer.java': '''package carpet.script;
import java.util.*;
import carpet.script.value.*;
public class CarpetEventServer {
    public static class Event {
        public static final Map<String, Event> byName = new HashMap<>();
        public final String name; public final boolean globalOnly;
        public final CallbackList handler;
        public Event(String name, int args, boolean globalOnly) {
            this.name=name; this.globalOnly=globalOnly; this.handler=new CallbackList(args); byName.put(name,this);
        }
        public boolean isNeeded() { return !handler.callList.isEmpty(); }
    }
    public static class CallbackList {
        public final int reqArgs;
        public final List<Callback> callList=new ArrayList<>();
        public CallbackList(int args) { reqArgs=args; }
    }
    public static class Callback {
        public final String host, optionalTarget;
        public final FunctionValue function;
        public final List<Value> parametrizedArgs;
        public Callback(String host, String target, FunctionValue function, List<Value> bound) {
            this.host=host; this.optionalTarget=target; this.function=function;
            this.parametrizedArgs=bound == null ? Collections.emptyList() : bound;
        }
    }
}
''',
'carpet/utils/CarpetProfiler.java': '''package carpet.utils;
public class CarpetProfiler {
    public enum TYPE { GENERAL }
    public static class ProfilerToken { }
    public static int started, ended;
    public static ProfilerToken start_section(Object world, String name, TYPE type) { started++; return new ProfilerToken(); }
    public static void end_current_section(ProfilerToken token) { ended++; }
}
''',
'carpet/script/PlayerCommandEventHarness.java': '''package carpet.script;
import java.util.*;
import carpet.CarpetServer;
import carpet.CarpetSettings;
import carpet.script.value.*;
import carpet.script.exception.IntegrityException;
import carpet.utils.CarpetProfiler;
import net.minecraft.server.network.ServerPlayerEntity;

public class PlayerCommandEventHarness {
    private static int checks;
    private static final ServerPlayerEntity ALICE = new ServerPlayerEntity("Alice");
    private static final ServerPlayerEntity BOB = new ServerPlayerEntity("Bob");
    private static void check(boolean ok, String why) { checks++; if (!ok) throw new AssertionError(why); }
    private static PlayerCommandEvent fresh() {
        CarpetServer.scriptServer=new CarpetScriptServer();
        CarpetSettings.runPermissionLevel=2;
        CarpetProfiler.started=0; CarpetProfiler.ended=0;
        return new PlayerCommandEvent();
    }
    private static CarpetEventServer.Callback add(PlayerCommandEvent event, String host, String target, int arity,
            FunctionValue.Body body, Value... bound) {
        CarpetEventServer.Callback cb = new CarpetEventServer.Callback(host, target,
                new FunctionValue(arity, body), Arrays.asList(bound));
        event.handler.callList.add(cb); return cb;
    }
    public static void main(String[] args) {
        PlayerCommandEvent event=fresh();
        check(CarpetEventServer.Event.byName.get("player_command") == event, "registered event");
        check(event.handler.reqArgs == 2 && !event.globalOnly, "player-event shape");
        check(!event.onCommand(ALICE,"help"), "no listeners allow execution");
        check(CarpetProfiler.started == 0, "no-listener fast path");
        add(event,null,null,2,(h,s,a)->new StringValue("cancel"));
        CarpetServer.scriptServer=null;
        check(!event.onCommand(ALICE,"help"), "stopped server allows execution");

        for (Value value : new Value[]{null,Value.NULL,Value.TRUE,Value.FALSE,new Value("1"),new StringValue(""),
                new StringValue("Cancel"),new StringValue("cancel "),new StringValue("other")}) {
            event=fresh();
            add(event,null,null,2,(h,s,a)->value);
            check(!event.onCommand(ALICE,"help"), "only exact cancel vetoes");
            check(event.handler.callList.size() == 1, "normal returns keep subscriptions");
        }
        event=fresh();
        final int[] notified={0};
        add(event,null,null,2,(h,s,a)->{notified[0]++; return new StringValue("cancel");});
        add(event,null,null,2,(h,s,a)->{notified[0]++; return Value.FALSE;});
        check(event.onCommand(ALICE,"help"), "cancel sticky across callbacks");
        check(notified[0] == 2, "cancel must not short-circuit observers");
        check(event.handler.callList.size() == 2, "cancel is not callback failure");
        check(CarpetProfiler.started == 1 && CarpetProfiler.ended == 1, "profiling balanced");

        event=fresh();
        CarpetSettings.runPermissionLevel=4;
        Value bound=new StringValue("bound");
        CarpetEventServer.Callback boundCallback=add(event,null,null,3,(h,s,a)->{
            check(s.level == 4 && s.getName().equals("Alice"), "permission and source preserved");
            check(((EntityValue)a.get(0)).entity == ALICE, "first argument player");
            check(a.get(1).getString().equals("say hello"), "second argument command");
            check(a.get(2) == bound, "bound arguments appended");
            return Value.NULL;
        },bound);
        check(!event.onCommand(ALICE,"say hello"), "bound callback executes normally");
        check(boundCallback.parametrizedArgs.size() == 1, "bound list not mutated");

        event=fresh();
        CarpetScriptHost root=new CarpetScriptHost(true), alice=new CarpetScriptHost(false), bob=new CarpetScriptHost(false);
        root.children.put("Alice",alice); root.children.put("Bob",bob);
        CarpetServer.scriptServer.modules.put("scoped",root);
        CarpetScriptHost global=new CarpetScriptHost(false);
        CarpetServer.scriptServer.modules.put("global",global);
        add(event,"scoped",null,2,(h,s,a)->{throw new AssertionError("template executed");});
        add(event,"scoped","Alice",2,(h,s,a)->{check(h == alice,"Alice's host"); return Value.NULL;});
        add(event,"scoped","Bob",2,(h,s,a)->{check(h == bob,"Bob's host"); return Value.NULL;});
        add(event,"global",null,2,(h,s,a)->Value.NULL);
        check(!event.onCommand(ALICE,"help"),"Alice command");
        check(alice.calls == 1 && bob.calls == 0 && global.calls == 1,"scope filtering");
        check(!event.onCommand(BOB,"help"),"Bob command");
        check(alice.calls == 1 && bob.calls == 1 && global.calls == 2,"both player scopes");
        check(event.handler.callList.size() == 4,"other player's subscriptions retained");

        event=fresh();
        add(event,"missing",null,2,(h,s,a)->new StringValue("cancel"));
        add(event,null,null,3,(h,s,a)->new StringValue("cancel"));
        add(event,null,null,2,(h,s,a)->{throw new NullPointerException("invalid callback");});
        add(event,null,null,2,(h,s,a)->{throw new IntegrityException("invalid callback");});
        add(event,null,null,2,(h,s,a)->Value.NULL);
        check(!event.onCommand(ALICE,"help"),"errors do not veto");
        check(event.handler.callList.size() == 1,"invalid callbacks removed");
        check(CarpetProfiler.ended == 1,"profiling closed on callback errors");

        final PlayerCommandEvent mutating=fresh();
        final int[] newCalls={0};
        add(mutating,null,null,2,(h,s,a)->{
            mutating.handler.callList.clear();
            add(mutating,null,null,2,(h2,s2,a2)->{newCalls[0]++; return new StringValue("cancel");});
            return Value.NULL;
        });
        add(mutating,null,null,2,(h,s,a)->{throw new AssertionError("unregistered callback executed");});
        check(!mutating.onCommand(ALICE,"help"),"mutation is safe");
        check(newCalls[0] == 0,"new callbacks wait until next dispatch");
        check(mutating.onCommand(ALICE,"help") && newCalls[0] == 1,"new callback works next time");

        event=fresh();
        add(event,null,null,2,(h,s,a)->new StringValue("cancel"));
        CarpetServer.scriptServer.stopAll=true;
        check(!event.onCommand(ALICE,"help"),"paused scripts allow command");
        check(event.handler.callList.size() == 1 && CarpetProfiler.started == 0,"paused subscriptions unchanged");
        CarpetServer.scriptServer.stopAll=false;
        check(event.onCommand(ALICE,"help"),"resumed scripts can veto");

        event=fresh();
        CarpetServer.scriptServer.modules.put("scoped",new CarpetScriptHost(true));
        add(event,"scoped","Alice",2,(h,s,a)->new StringValue("cancel"));
        check(!event.onCommand(ALICE,"help") && event.handler.callList.isEmpty(),"missing target cleaned up");
        System.out.println("PASS: " + checks + " command-event assertions");
    }
}
''',
}


class CommandEventTests(unittest.TestCase):
    def test_dispatcher_behavior_with_java8_bytecode(self):
        output = run_java('carpet.script.PlayerCommandEventHarness', [
            'carpet/script/PlayerCommandEvent.java',
            'carpet/script/exception/InvalidCallbackException.java',
            'carpet/script/exception/IntegrityException.java',
        ], STUBS)
        self.assertIn('command-event assertions', output)

    def test_hook_is_command_only_and_cancellable(self):
        source = (ROOT / 'src/main/java/carpet/mixins/ServerPlayNetworkHandler_scarpetEventsMixin.java').read_text()
        self.assertIn('@Inject(method = "executeCommand", at = @At("HEAD"), cancellable = true)', source)
        self.assertIn('command.startsWith("/") ? command.substring(1) : command', source)
        self.assertEqual(1, source.count('cancellable = true'), 'Other event injections must remain unchanged')
        self.assertIn('ci.cancel();', source)

    def test_event_is_registered_without_replacing_other_dispatch(self):
        source = (ROOT / 'src/main/java/carpet/script/CarpetEventServer.java').read_text()
        self.assertIn('public static final PlayerCommandEvent PLAYER_COMMAND = new PlayerCommandEvent();', source)
        self.assertIn('public void call(Supplier<List<Value>> argumentSupplier', source)
        self.assertIn('public boolean execute(ServerCommandSource sender, List<Value> runtimeArgs)', source)


if __name__ == '__main__':
    unittest.main()
