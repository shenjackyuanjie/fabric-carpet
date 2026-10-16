"""Check localized call sites, Java formatter contracts and frozen rule/command IDs."""
from collections import Counter
import hashlib
import json
import re
import unittest
from java_harness import ROOT, run_java
from test_localization import STRING, TOKENS, rules_from_source, without_comments

MESSAGE_FILES = [
    'carpet/CarpetSettings.java', 'carpet/settings/SettingsManager.java',
    'carpet/settings/ParsedRule.java', 'carpet/settings/Validator.java',
    'carpet/commands/LogCommand.java', 'carpet/commands/PlayerCommand.java',
    'carpet/script/utils/AppStoreManager.java',
]
COMMAND_FILES = [
    'carpet/commands/LogCommand.java', 'carpet/commands/PlayerCommand.java',
    'carpet/settings/SettingsManager.java',
]
# Frozen branch templates use strings only; reject unfamiliar formatting rather than guessing.
FORMAT = re.compile(r'%(?:(\d+)\$)?([sS%n])')


def literal_translations(source):
    tokens = TOKENS.findall(without_comments(source))
    for i in range(len(tokens) - 5):
        if tokens[i:i + 2] != ['tr', '('] or not tokens[i + 2].startswith('"') or tokens[i + 3] != ',':
            continue
        j, parts = i + 4, []
        while j < len(tokens) and tokens[j].startswith('"'):
            parts.append(json.loads(tokens[j]))
            j += 1
            if tokens[j] != '+':
                break
            j += 1
        if parts and tokens[j] == ')':
            yield json.loads(tokens[i + 2]), ''.join(parts)


def format_signature(text):
    result = []
    implicit_index, i = 0, 0
    while i < len(text):
        if text[i] != '%':
            i += 1
            continue
        match = FORMAT.match(text, i)
        if match is None:
            raise AssertionError('Malformed format string: ' + text)
        conversion = match.group(2)
        if conversion not in ('%', 'n'):
            if match.group(1):
                index = int(match.group(1))
            else:
                implicit_index += 1
                index = implicit_index
            result.append((index, conversion.lower()))
        i = match.end()
    return Counter(result)


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def rule_contract_digest(source):
    cleaned = without_comments(source)
    result = {}
    for name, annotation in rules_from_source(source).items():
        field = re.search(r'\bpublic\s+static\s+[\w<>]+\s+' + re.escape(name) + r'\s*[^;]*;', cleaned)
        if field is None:
            raise AssertionError('Cannot locate rule declaration ' + name)
        result[name] = {'annotation': annotation, 'declaration': TOKENS.findall(field.group())}
    return digest(result)


def command_contract_digest(source):
    return digest(re.findall(r'\b(literal|argument)\(\s*(' + STRING + ')', without_comments(source)))


class LocalizedMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zh = json.loads((ROOT / 'src/main/resources/assets/carpet/lang/zh_cn.json').read_text(encoding='utf-8'))
        cls.calls = []
        for name in MESSAGE_FILES:
            cls.calls.extend(literal_translations((ROOT / 'src/main/java' / name).read_text(encoding='utf-8')))

    def test_all_literal_call_sites_have_matching_placeholders(self):
        self.assertGreaterEqual(len(self.calls), 60)
        for key, fallback in self.calls:
            with self.subTest(key=key):
                self.assertIn(key, self.zh)
                self.assertEqual(format_signature(fallback), format_signature(self.zh[key]))

    def test_actual_java_formatter_accepts_templates(self):
        statements = []
        for key, fallback in self.calls:
            if key not in self.zh:
                continue
            signature = format_signature(fallback)
            count = max((index for index, _ in signature), default=0)
            # All localized call sites currently use %s. Fail rather than invent a test value for a new conversion.
            self.assertTrue(all(kind == 's' for _, kind in signature))
            arguments = ','.join('"value%with-percent"' for _ in range(count))
            text = json.dumps(self.zh[key], ensure_ascii=True)
            statements.append('String.format(java.util.Locale.ROOT, ' + text + ', new Object[]{' + arguments + '});')
        code = 'public class FormatHarness { public static void main(String[] args) {'
        code += '\n'.join(statements) + 'System.out.println("PASS formatter");}}'
        self.assertIn('PASS formatter', run_java('FormatHarness', [], {'FormatHarness.java': code}))

    def test_rule_definitions_defaults_and_command_identifiers_are_unchanged(self):
        golden = json.loads((ROOT / 'tests/fixtures/1.16.5-contracts.json').read_text())
        source = (ROOT / 'src/main/java/carpet/CarpetSettings.java').read_text()
        self.assertEqual(golden['rules'], rule_contract_digest(source))
        for name in COMMAND_FILES:
            with self.subTest(file=name):
                source = (ROOT / 'src/main/java' / name).read_text()
                self.assertEqual(golden['commands'][name], command_contract_digest(source))

    def test_loader_uses_its_argument_and_retains_null_fallback(self):
        source = (ROOT / 'src/main/java/carpet/utils/Translations.java').read_text()
        self.assertIn('getResourceAsStream(path)', source)
        self.assertIn('try (InputStream stream =', source)
        self.assertIn('if (stream == null) return null;', source)
        self.assertIn('translationMap == null ? str : translationMap.getOrDefault(key, str)', source)

    def test_detail_menu_uses_the_existing_ui_key(self):
        source = (ROOT / 'src/main/java/carpet/settings/SettingsManager.java').read_text()
        self.assertNotIn('tr("list_all_%s_settings"', source)
        self.assertNotIn('"^g refresh"', source)
        self.assertNotIn('"w Options: "', source)
        self.assertIn('Translations.matchesTranslation("rule." + rule.name + ".name", lcSearch)', source)
        self.assertIn('Translations.matchesTranslation("rule." + rule.name + ".desc", lcSearch)', source)

    def test_explicit_argument_reordering_is_supported(self):
        self.assertEqual(format_signature('%s from %s'), format_signature('%2$s: %1$s'))
        self.assertNotEqual(format_signature('%s'), format_signature('%s %s'))
        with self.assertRaises(AssertionError):
            format_signature('%(broken)s')


if __name__ == '__main__':
    unittest.main()
