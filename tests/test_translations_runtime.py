"""Run the actual translation loader/map code with explicit external API stand-ins.

Gson parsing itself is not mocked as a test target: JSON is validated separately.
Its stand-in records the input and supplies a controlled map for dispatch tests.
"""
import unittest
from java_harness import run_java

STUBS = {
'carpet/CarpetExtension.java': '''package carpet;
import java.util.Map;
public interface CarpetExtension { Map<String,String> canHasTranslations(String language); }
''',
'carpet/CarpetServer.java': '''package carpet;
import java.util.*;
public class CarpetServer { public static final List<CarpetExtension> extensions=new ArrayList<>(); }
''',
'carpet/CarpetSettings.java': '''package carpet;
public class CarpetSettings { public static String language="none"; }
''',
'net/minecraft/server/command/ServerCommandSource.java': '''package net.minecraft.server.command;
public class ServerCommandSource { }
''',
'com/google/gson/Gson.java': '''package com.google.gson;
import java.lang.reflect.Type;
import java.util.*;
public class Gson {
    public static String lastInput;
    public static Map<String,String> nextResult=new HashMap<>();
    @SuppressWarnings("unchecked")
    public <T> T fromJson(String input, Type type) { lastInput=input; return (T)new HashMap<>(nextResult); }
}
''',
'com/google/gson/GsonBuilder.java': '''package com.google.gson;
public class GsonBuilder {
    public GsonBuilder enableComplexMapKeySerialization() { return this; }
    public Gson create() { return new Gson(); }
}
''',
'com/google/gson/reflect/TypeToken.java': '''package com.google.gson.reflect;
import java.lang.reflect.Type;
public class TypeToken<T> { public Type getType() { return Object.class; } }
''',
'org/apache/commons/io/IOUtils.java': '''package org.apache.commons.io;
import java.io.*;
import java.nio.charset.Charset;
public class IOUtils {
    public static InputStream lastStream;
    public static String toString(InputStream input, Charset charset) throws IOException {
        lastStream=input;
        ByteArrayOutputStream output=new ByteArrayOutputStream();
        byte[] buffer=new byte[256]; int count;
        while ((count=input.read(buffer)) != -1) output.write(buffer,0,count);
        return new String(output.toByteArray(),charset);
    }
}
''',
'TranslationsHarness.java': '''import java.io.IOException;
import java.util.*;
import carpet.*;
import carpet.utils.Translations;
import com.google.gson.Gson;
import org.apache.commons.io.IOUtils;

public class TranslationsHarness {
    private static int checks;
    private static void check(boolean ok, String why) { checks++; if (!ok) throw new AssertionError(why); }
    public static void main(String[] args) throws Exception {
        CarpetSettings.language="none";
        Translations.updateLanguage(null);
        check(!Translations.hasTranslations(),"none has no map");
        check(Translations.tr("missing").equals("missing"),"one-argument fallback");
        check(Translations.tr("missing","English").equals("English"),"English fallback");
        check(!Translations.matchesTranslation("missing","missing"),"never search missing-key fallback");

        CarpetSettings.language="not-the-requested-path";
        Gson.nextResult.put("marker","自定义");
        Map<String,String> custom=Translations.getTranslationFromResourcePath("fixtures/custom.json");
        check(custom != null && custom.get("marker").equals("自定义"),"explicit resource path is honored");
        check(Gson.lastInput.contains("自定义"),"resource input decoded as UTF-8");
        boolean closed=false;
        try { IOUtils.lastStream.read(); } catch (IOException expected) { closed=true; }
        check(closed,"resource stream is closed");
        check(Translations.getTranslationFromResourcePath("missing/file.json") == null,"missing-resource API stays null");

        Gson.nextResult.clear();
        Gson.nextResult.put("rule.pushLimit.name","活塞推动上限");
        Gson.nextResult.put("title","core");
        Gson.nextResult.put("inventory","INVENTORY");
        CarpetServer.extensions.add(language -> {
            Map<String,String> map=new HashMap<>();
            map.put("title","extension must not override core");
            map.put("extension.only","扩展");
            map.put("//comment","ignored");
            return map;
        });
        CarpetServer.extensions.add(language -> null);
        CarpetSettings.language="zh_cn";
        Translations.updateLanguage(null);
        check(Translations.hasTranslations(),"language map loaded");
        check(Translations.tr("title").equals("core"),"core translation precedence preserved");
        check(Translations.tr("extension.only").equals("扩展"),"extension fills missing keys");
        check(!Translations.hasTranslation("//comment"),"comment keys removed");
        check(Translations.matchesTranslation("rule.pushLimit.name","推动"),"Chinese substring search");
        check(!Translations.matchesTranslation("rule.pushLimit.name","unrelated"),"unmatched Chinese search");
        Locale previous=Locale.getDefault();
        try {
            Locale.setDefault(new Locale("tr","TR"));
            check(Translations.matchesTranslation("inventory","inventory"),"search uses Locale.ROOT");
        } finally { Locale.setDefault(previous); }
        check(Translations.tr("not.translated","fallback").equals("fallback"),"partial map keeps fallback");

        CarpetSettings.language="NoNe";
        Translations.updateLanguage(null);
        check(!Translations.hasTranslations() && !Translations.hasTranslation("title"),"none clears stale translations");
        check(Translations.tr("title","English").equals("English"),"language switch restores English");
        CarpetServer.extensions.clear();
        CarpetSettings.language="missing_language";
        Translations.updateLanguage(null);
        check(!Translations.hasTranslations(),"unknown empty language clears map");
        check(Translations.tr("title","English").equals("English"),"unknown language fallback");
        System.out.println("PASS: " + checks + " translation assertions");
    }
}
''',
}


class TranslationRuntimeTests(unittest.TestCase):
    def test_loading_switching_fallback_search_and_extension_precedence(self):
        output = run_java('TranslationsHarness', ['carpet/utils/Translations.java'], STUBS, {
            'fixtures/custom.json': '{"marker":"自定义"}',
            'assets/carpet/lang/zh_cn.json': '{"title":"core"}',
        })
        self.assertIn('translation assertions', output)


if __name__ == '__main__':
    unittest.main()
