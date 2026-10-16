"""Resource-only regression checks for the frozen Minecraft 1.16.5 branch."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
STRING = r'"(?:\\.|[^"\\])*"'
LEXEMES = re.compile(STRING + r"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*.*?\*/", re.S)
TOKENS = re.compile(STRING + r'|[A-Za-z_$][\w$]*|[^\s]')


def without_comments(source):
    return LEXEMES.sub(lambda m: ' ' if m.group().startswith(('//', '/*')) else m.group(), source)


def annotation_values(tokens, name):
    for i in range(len(tokens) - 2):
        if tokens[i:i + 2] != [name, '=']:
            continue
        start = i + 2
        if tokens[start] != '{':
            return [tokens[start]]
        end = tokens.index('}', start)
        return [t for t in tokens[start + 1:end] if t != ',']
    return []


def rules_from_source(source):
    source = without_comments(source)
    rules = {}
    for match in re.finditer(r'@Rule\s*\(', source):
        start = match.end()
        i, depth = start, 1
        while depth:
            if i >= len(source):
                raise AssertionError('Unterminated @Rule annotation')
            if source[i] == '"':
                literal = re.match(STRING, source[i:])
                if literal is None:
                    raise AssertionError('Invalid Java string in @Rule')
                i += literal.end()
                continue
            depth += (source[i] == '(') - (source[i] == ')')
            i += 1
        field = re.match(r'\s*public\s+static\s+[\w<>]+\s+(\w+)\s*(?:=|;)', source[i:])
        if field is None:
            raise AssertionError('Could not find field after @Rule')
        tokens = TOKENS.findall(source[start:i - 1])
        name = field.group(1)
        override = annotation_values(tokens, 'name')
        if override and json.loads(override[0]):
            name = json.loads(override[0])
        if name in rules:
            raise AssertionError('Duplicate rule ' + name)
        rules[name] = tokens
    return rules


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError('Duplicate translation key ' + key)
        result[key] = value
    return result


class LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.translations = json.loads(
            (ROOT / 'src/main/resources/assets/carpet/lang/zh_cn.json').read_text(encoding='utf-8'),
            object_pairs_hook=unique_pairs,
        )
        cls.rules = rules_from_source(
            (ROOT / 'src/main/java/carpet/CarpetSettings.java').read_text(encoding='utf-8')
        )

    def test_all_82_active_rules_have_names_and_descriptions(self):
        self.assertEqual(82, len(self.rules), 'Unexpected gameplay rule changes on the frozen branch')
        for suffix in ('name', 'desc'):
            translated = {k.split('.')[1] for k in self.translations if k.startswith('rule.') and k.endswith('.' + suffix)}
            self.assertEqual(set(self.rules), translated)

    def test_all_additional_notes_are_present_and_contiguous(self):
        for name, annotation in self.rules.items():
            with self.subTest(rule=name):
                expected = len(annotation_values(annotation, 'extra'))
                prefix = 'rule.' + name + '.extra.'
                actual = sorted(int(k[len(prefix):]) for k in self.translations if k.startswith(prefix))
                self.assertEqual(list(range(len(actual))), actual)
                self.assertGreaterEqual(len(actual), expected, 'A partial extra list hides the remaining English notes')

    def test_all_used_categories_are_translated(self):
        for annotation in self.rules.values():
            for category in annotation_values(annotation, 'category'):
                name = json.loads(category) if category.startswith('"') else category.lower()
                self.assertIn('category.' + name, self.translations)

    def test_values_are_nonempty_strings(self):
        for key, value in self.translations.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, str)
                self.assertTrue(value.strip())

    def test_version_specific_corrections(self):
        tr = self.translations
        self.assertIn('弧度', tr['rule.hardcodeTNTangle.extra.0'])
        self.assertIn('小于 2π', tr['rule.hardcodeTNTangle.extra.0'])
        self.assertIn('子集', tr['rule.commandProfile.extra.0'])
        self.assertIn('纯客户端', tr['rule.creativeFlySpeed.extra.0'])
        self.assertIn('纯客户端', tr['rule.creativeFlyDrag.extra.3'])
        self.assertIn('玻璃', tr['rule.missingTools.desc'])
        self.assertIn('生物', tr['rule.flatWorldStructureSpawning.desc'])
        self.assertNotIn('%', tr['ui.switch_to'])

    def test_comment_parser_does_not_count_disabled_rules(self):
        source = '// @Rule(desc="disabled") public static boolean disabled;\n'
        source += '/* @Rule(desc="disabled") public static boolean alsoDisabled; */\n'
        source += '@Rule(desc="https://example.test/a", extra={"x", "y"}, category={FEATURE,"extras"}) public static boolean active = false;'
        parsed = rules_from_source(source)
        self.assertEqual(['active'], list(parsed))
        self.assertEqual(['"x"', '"y"'], annotation_values(parsed['active'], 'extra'))


if __name__ == '__main__':
    unittest.main()
