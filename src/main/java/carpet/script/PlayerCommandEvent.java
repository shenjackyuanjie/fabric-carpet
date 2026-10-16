package carpet.script;

import carpet.CarpetServer;
import carpet.CarpetSettings;
import carpet.script.exception.IntegrityException;
import carpet.script.exception.InvalidCallbackException;
import carpet.script.value.EntityValue;
import carpet.script.value.StringValue;
import carpet.script.value.Value;
import carpet.utils.CarpetProfiler;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.util.math.BlockPos;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * A narrowly scoped backport: only player_command consumes callback results.
 * The existing dispatch and return-value contracts of other events are unchanged.
 */
public final class PlayerCommandEvent extends CarpetEventServer.Event
{
    PlayerCommandEvent()
    {
        super("player_command", 2, false);
    }

    /** Called on the server thread for a player-originated command, without '/'. */
    public boolean onCommand(ServerPlayerEntity player, String command)
    {
        CarpetScriptServer scriptServer = CarpetServer.scriptServer;
        if (scriptServer == null || scriptServer.stopAll || !isNeeded()) return false;

        CarpetProfiler.ProfilerToken token = CarpetProfiler.start_section(null, "Scarpet events", CarpetProfiler.TYPE.GENERAL);
        List<CarpetEventServer.Callback> failed = new ArrayList<>();
        boolean cancelled = false;
        try
        {
            ServerCommandSource source = player.getCommandSource().withLevel(CarpetSettings.runPermissionLevel);
            List<Value> runtimeArgs = Arrays.asList(new EntityValue(player), new StringValue(command));
            // Callbacks can unregister themselves, unload apps or register new callbacks.
            for (CarpetEventServer.Callback callback : new ArrayList<>(handler.callList))
            {
                if (!handler.callList.contains(callback)) continue;
                if (callback.optionalTarget != null && !source.getName().equals(callback.optionalTarget)) continue;

                CarpetScriptHost host = callback.host == null ? scriptServer.globalHost : scriptServer.modules.get(callback.host);
                if (host == null)
                {
                    failed.add(callback);
                    continue;
                }
                // The global template of a player-scoped app is not an executing instance.
                if (host.isPerUser() && callback.optionalTarget == null) continue;
                // The anonymous global host cannot be targeted at a player instance.
                if (callback.host == null && callback.optionalTarget != null) continue;

                List<Value> args = new ArrayList<>(runtimeArgs);
                args.addAll(callback.parametrizedArgs);
                try
                {
                    List<CarpetScriptHost> targets = host.retrieveForExecution(source, callback.optionalTarget);
                    if (targets.isEmpty()) failed.add(callback);
                    for (CarpetScriptHost target : targets)
                    {
                        Value result = target.callUDF(BlockPos.ORIGIN, source, callback.function, args);
                        if (result != null && "cancel".equals(result.getString())) cancelled = true;
                    }
                }
                catch (NullPointerException | InvalidCallbackException | IntegrityException invalid)
                {
                    // Match old event dispatch's invalid-callback cleanup; an error is not a veto.
                    failed.add(callback);
                }
                // Do not short-circuit after cancellation: notify all remaining observers.
            }
        }
        finally
        {
            handler.callList.removeAll(failed);
            CarpetProfiler.end_current_section(token);
        }
        return cancelled;
    }
}
