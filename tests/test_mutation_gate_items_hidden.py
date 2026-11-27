"""R24, R34: Rust hidden-code items of the mutation-gate-items check.

The token-level tests need no cargo. The fixture tests copy the tracked
`amicable/amicable-rs` sources into a throwaway git repo (see `RustCase`); the only cargo
call the script makes there is `cargo mutants --list`, and nothing is ever built.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.test_mutation_gate_items_rust import CRATE, RustCase, mgi

LIB = "src/lib.rs"
SKIP_SPELLED = "#[ mutants :: skip ]\npub fn a() -> u32 {\n    1\n}\n"
SKIP_SPLIT = "#[mutants\n::\nskip]\npub fn a() -> u32 {\n    1\n}\n"
SKIP_COMMENTED = "#[mutants /* x */ :: // y\n skip]\npub fn a() -> u32 {\n    1\n}\n"
SKIP_CFG_ATTR = "#[cfg_attr(test, mutants::skip)]\npub fn a() -> u32 {\n    1\n}\n"
MACRO_RULES = "macro_rules! m {\n    () => {};\n}\n"
INVOCATION_ITEMS = {
    "vec_arith": "fn t(a: u32, b: u32) -> u32 { vec![a * b + 1][0] }",
    "dbg_arith": "fn t(a: u32, b: u32) -> u32 { dbg!(a * b) }",
    "vec_match": "fn t(a: u32) -> u32 { vec![match a { 0 => 7, _ => 3 }][0] }",
    "vec_struct_update": "fn t(a: u32) -> u32 { vec![S { a, ..Default::default() }][0].a }",
    "matches_guard": "fn t(a: u32, b: u32) -> bool { matches!(a, _ if a * b > 10) }",
    "format_arith": 'fn t(a: u32) -> String { format!("{}", a+1) }',
    "infix_and": "fn t(a: u32, b: u32) -> u32 { dbg!(&a & b) }",
    "negative": "fn t() -> i32 { dbg!(-1) }",
    "question": "fn t(a: Option<u32>) -> Option<u32> { Some(dbg!(a?)) }",
    "cast": "fn t(a: u32) -> u64 { dbg!(a as u64) }",
}
INVOCATION_CLEAN = {
    "println_literal_and_ident": 'fn t(x: u32) -> u32 { println!("{}", x); x }',
    "assert_eq_method": "fn t(a: &[u32]) { assert_eq!(a.len(), 3); }",
    "write_field": 'fn t(f: &mut String, s: &S) { let _ = write!(f, "{}", s.x); }',
    "prefix_ref": "fn t(a: u32, b: u32) { dbg!(&a, &mut b.clone()); }",
    "tuple_field": "fn t(a: (u32, u32)) -> u32 { dbg!(a.0) }",
    "path_arg": "fn t() -> u32 { dbg!(std::u32::MAX) }",
    "empty": "fn t() -> Vec<u32> { vec![] }",
    "nested_allowed": 'fn t(x: u32) { println!("{}", format!("{}", x)); }',
}


class TokenizerTest(unittest.TestCase):
    """The scanner survives every literal shape that could hide a brace or a comment."""

    def kinds(self, text: str) -> list[tuple[str, str]]:
        return [(t.kind, t.text) for t in mgi.rust_tokens(text)]

    def test_comments_vanish_and_block_comments_nest(self) -> None:
        text = "a /* x /* y */ still */ b // c\nd"
        self.assertEqual([t for _, t in self.kinds(text)], ["a", "b", "d"])

    def test_unclosed_block_comment_ends_at_end_of_text(self) -> None:
        self.assertEqual(self.kinds("a /* never closed"), [("ident", "a")])

    def test_string_forms_are_single_tokens(self) -> None:
        text = r'"a\"}" r#"}"#  br##"x"y"## b"z" c"w"'
        self.assertEqual({k for k, _ in self.kinds(text)}, {"str"})
        self.assertEqual(len(self.kinds(text)), 5)

    def test_char_versus_lifetime(self) -> None:
        got = self.kinds("'a' '\\n' '{' 'static b'x' <'a>")
        self.assertEqual(
            [k for k, _ in got],
            ["char", "char", "char", "life", "char", "punct", "life", "punct"],
        )

    def test_numbers_keep_their_fraction_but_not_a_range(self) -> None:
        self.assertEqual(
            [t for _, t in self.kinds("1.5 1..2 x.0")][:4], ["1.5", "1", ".", "."]
        )

    def test_path_separator_is_one_token(self) -> None:
        self.assertEqual(self.kinds("a::b")[1], ("punct", "::"))


class TestMaskTest(unittest.TestCase):
    """`#[cfg(test)]` items are exempt; nothing else is, however they are written."""

    def hidden(self, text: str) -> list[str]:
        return mgi.hidden_texts(text)

    def test_prop_assert_in_cfg_test_mod_is_not_an_item(self) -> None:
        text = "#[cfg(test)]\nmod tests {\n    fn t() { prop_assert!(x == y); }\n}\n"
        self.assertEqual(self.hidden(text), [])

    def test_span_ends_at_the_matching_brace_despite_literal_braces(self) -> None:
        inner = 'let c = \'}\'; let s = "}}"; let r = r#"}"#; /* } */ // }\n'
        text = f"#[cfg(test)]\nmod t {{ fn f() {{ {inner} }} }}\ndbg!(a * b);\n"
        self.assertEqual(self.hidden(text), ["dbg ! ( a * b )"])

    def test_skip_inside_cfg_test_is_not_an_item(self) -> None:
        text = "#[cfg(test)]\nmod t {\n    #[mutants::skip]\n    fn f() {}\n}\n"
        self.assertEqual(self.hidden(text), [])

    def test_cfg_not_test_and_cfg_attr_are_still_examined(self) -> None:
        text = "#[cfg(not(test))]\nmod t { fn f() { dbg!(a * b); } }\n"
        self.assertEqual(self.hidden(text), ["dbg ! ( a * b )"])

    def test_inner_cfg_test_exempts_the_whole_file(self) -> None:
        self.assertEqual(self.hidden("#![cfg(test)]\ndbg!(a * b);\n"), [])

    def test_cfg_test_gates_a_single_fn_and_an_out_of_line_mod(self) -> None:
        text = "#[cfg(test)]\nfn f() { dbg!(a * b); }\n#[cfg(test)]\nmod tests;\ndbg!(c + d);\n"
        self.assertEqual(self.hidden(text), ["dbg ! ( c + d )"])

    def test_unclosed_test_mod_does_not_crash_and_exempts_the_rest(self) -> None:
        self.assertEqual(self.hidden("#[cfg(test)]\nmod t {\n dbg!(a * b);\n"), [])

    def test_empty_text_has_no_items(self) -> None:
        self.assertEqual(self.hidden(""), [])


class MaskSpillTest(unittest.TestCase):
    """A `cfg(test)` attribute exempts only what it gates, never code after it."""

    BAD = "fn f() { dbg!(a * b); }\n"

    def test_decoys_leave_following_code_examined(self) -> None:
        decoys = {
            "inner_attr_in_mod": "mod m { #![cfg(test)] }\n",
            "inner_attr_in_fn": "fn d() { #![cfg(test)] }\n",
            "struct_field": "struct S { #[cfg(test)] x: u32, y: u32 }\n",
            "struct_last_field": "struct S { #[cfg(test)] x: u32 }\n",
            "enum_variant": "enum E { #[cfg(test)] A, B }\n",
            "enum_last_variant": "enum E { A, #[cfg(test)] B }\n",
            "match_arm": "fn m(a: u32) -> u32 { match a { #[cfg(test)] 1 => 2, _ => 3 } }\n",
            "param": "fn p(#[cfg(test)] a: u32, b: u32) {}\n",
            "last_param": "fn p(a: u32, #[cfg(test)] b: u32) {}\n",
            "tuple_field": "struct T(#[cfg(test)] u32, u32);\n",
        }
        for name, text in decoys.items():
            with self.subTest(decoy=name):
                self.assertEqual(mgi.hidden_texts(text + self.BAD), ["dbg ! ( a * b )"])

    def test_inner_attr_after_an_item_does_not_exempt_the_file(self) -> None:
        text = "fn first() {}\n#![cfg(test)]\n" + self.BAD
        self.assertEqual(mgi.hidden_texts(text), ["dbg ! ( a * b )"])

    def test_inner_attr_after_other_inner_attrs_still_exempts_the_file(self) -> None:
        text = "#![allow(dead_code)]\n#![cfg(test)]\nfn first() {}\n" + self.BAD
        self.assertEqual(mgi.hidden_texts(text), [])

    def test_inner_attr_exempts_up_to_the_enclosing_block_only(self) -> None:
        text = "mod m { #![cfg(test)] " + self.BAD + "}\n" + self.BAD
        self.assertEqual(mgi.hidden_texts(text), ["dbg ! ( a * b )"])

    def test_gated_items_stay_exempt_through_generics_and_fields(self) -> None:
        gated = (
            "#[cfg(test)] fn g<T, U>(a: T, b: U) { dbg!(a * b); }\n"
            "#[cfg(test)] pub(crate) fn h() { dbg!(a * b); }\n"
            "#[cfg(test)] struct S { a: u32, b: u32 }\n"
            "#[cfg(test)] impl<T, U> X<T, U> { fn m() { dbg!(a * b); } }\n"
            "#[cfg(test)] use std::fmt;\n"
        )
        self.assertEqual(mgi.hidden_texts(gated), [])
        self.assertEqual(mgi.hidden_texts(gated + self.BAD), ["dbg ! ( a * b )"])


class IncludeAndPathTest(unittest.TestCase):
    def test_include_is_an_item_whatever_its_arguments(self) -> None:
        for text in (
            'include!("../extra.rs");',
            'include!(concat!(env!("X"), "/y.rs"));',
        ):
            with self.subTest(text=text):
                self.assertTrue(
                    any(t.startswith("include !") for t in mgi.hidden_texts(text))
                )

    def test_include_str_and_include_bytes_are_not_items(self) -> None:
        text = 'const A: &str = include_str!("a.txt"); const B: &[u8] = include_bytes!("b");'
        self.assertEqual(mgi.hidden_texts(text), [])

    def test_path_attribute_is_an_item_in_any_spelling(self) -> None:
        for text in (
            '#[path = "../extra.rs"] pub mod h;',
            '#[ path="../extra.rs" ]\npub mod h;',
            '#[cfg_attr(unix, path = "../extra.rs")] mod h;',
        ):
            with self.subTest(text=text):
                self.assertEqual(len(mgi.hidden_texts(text)), 1)

    def test_a_path_that_is_not_the_attribute_is_not_an_item(self) -> None:
        text = "#[derive(Debug)] struct S { path: u32 }\nfn f(path: u32) { let _ = path; }\n"
        self.assertEqual(mgi.hidden_texts(text), [])

    def test_gated_by_cfg_test_they_are_exempt(self) -> None:
        text = '#[cfg(test)]\nmod t { include!("x.rs"); }\n'
        self.assertEqual(mgi.hidden_texts(text), [])


class SkipSpellingTest(unittest.TestCase):
    def test_every_spelling_is_an_item_and_normalises_alike(self) -> None:
        spelled = [SKIP_SPELLED, SKIP_SPLIT, SKIP_COMMENTED]
        texts = [mgi.hidden_texts(s) for s in spelled]
        self.assertEqual(texts, [["# [ mutants :: skip ]"]] * 3)

    def test_cfg_attr_spelling_is_an_item(self) -> None:
        got = mgi.hidden_texts(SKIP_CFG_ATTR)
        self.assertEqual(got, ["# [ cfg_attr ( test , mutants :: skip ) ]"])

    def test_mention_in_string_or_comment_is_not_an_item(self) -> None:
        text = 'fn s() -> &\'static str { "mutants::skip" }\n// mutants::skip\n'
        self.assertEqual(mgi.hidden_texts(text), [])

    def test_a_longer_path_is_not_the_skip_attribute(self) -> None:
        self.assertEqual(mgi.hidden_texts("#[xmutants::skip]\nfn f() {}\n"), [])


class MacroRuleTest(unittest.TestCase):
    def test_macro_rules_is_an_item_keyed_by_name(self) -> None:
        self.assertEqual(mgi.hidden_texts(MACRO_RULES), ["macro_rules ! m"])

    def test_invocation_items_and_clean_cases(self) -> None:
        for name, text in INVOCATION_ITEMS.items():
            with self.subTest(item=name):
                self.assertEqual(len(mgi.hidden_texts(text)), 1)
        for name, text in INVOCATION_CLEAN.items():
            with self.subTest(clean=name):
                self.assertEqual(mgi.hidden_texts(text), [])

    def test_ampersand_is_prefix_after_start_comma_paren_or_ampersand(self) -> None:
        for text in ("x!(&a)", "x!(a, &b)", "x!(f(&a))", "x!(&&a)"):
            with self.subTest(text=text):
                self.assertEqual(mgi.hidden_texts(text), [])
        for text in ("x!(a & b)", "x!(a && b)", "x!(&a & &b)", "x!(f(a) & b)"):
            with self.subTest(text=text):
                self.assertEqual(len(mgi.hidden_texts(text)), 1)

    def test_dot_is_access_only_between_a_value_and_a_name(self) -> None:
        self.assertEqual(mgi.hidden_texts("x!(a.b.c(d.e))"), [])
        for text in ("x!(a..b)", "x!(.a)", "x!(a.)"):
            with self.subTest(text=text):
                self.assertEqual(len(mgi.hidden_texts(text)), 1)

    def test_a_bare_group_or_brace_or_index_is_an_item(self) -> None:
        for text in ("x!((a))", "x!({ a })", "x!(a[0])", "x!(a; 3)"):
            with self.subTest(text=text):
                self.assertEqual(len(mgi.hidden_texts(text)), 1)

    def test_bracket_and_brace_invocations_are_judged_like_parens(self) -> None:
        self.assertEqual(mgi.hidden_texts("x![a, b]"), [])
        self.assertEqual(len(mgi.hidden_texts("x!{ a + b }")), 1)

    def test_keyword_then_not_is_negation_not_a_macro_call(self) -> None:
        text = "fn f(a: u32, b: u32) { if !(a > b) {} while !(a < b) {} }"
        self.assertEqual(mgi.hidden_texts(text), [])

    def test_not_equal_is_not_a_macro_call(self) -> None:
        self.assertEqual(mgi.hidden_texts("fn f(a: u32) -> bool { a != (3) }"), [])

    def test_spelling_and_layout_do_not_change_the_key(self) -> None:
        one = mgi.hidden_texts("dbg!(a*b)")
        two = mgi.hidden_texts("dbg! (\n  a /* c */ * b\n)")
        self.assertEqual(one, two)


class FunctionIdsTest(unittest.TestCase):
    def test_paths_use_enclosing_mod_and_impl(self) -> None:
        text = "mod a { impl X { fn g() {} } fn h() {} } fn k() {}"
        self.assertEqual(
            mgi.function_ids(text), {("k",), ("a", "h"), ("a", "impl X", "g")}
        )

    def test_bodyless_test_and_cfg_test_functions_are_not_counted(self) -> None:
        text = (
            "trait T { fn decl(); fn dflt() {} }\n"
            "#[test] fn t1() {}\n#[cfg(test)] fn t2() {}\n"
            "#[cfg(test)] mod m { fn t3() {} }\n"
            "pub(crate) const fn real() {}\n"
        )
        self.assertEqual(mgi.function_ids(text), {("trait T", "dflt"), ("real",)})

    def test_impl_trait_in_a_signature_is_not_a_container(self) -> None:
        got = mgi.function_ids("fn f() -> impl Iterator<Item = u32> { g() }")
        self.assertEqual(got, {("f",)})


class HiddenFixtureCase(RustCase):
    """The collector on a crate copy: head differs from base by one edit."""

    def append_lib(self, extra: str) -> None:
        self.edit(LIB, self.crate_path(LIB).read_text() + "\n" + extra)

    def hidden(self) -> list[Any]:
        self.commit("change")
        head = self.rev("HEAD")
        changed = mgi._changed_paths(self.repo, self.base, head)
        with tempfile.TemporaryDirectory() as tmp:
            ctx = mgi.Context(self.repo, self.base, head, changed, Path(tmp))
            return mgi.collect_rust_hidden(ctx)

    def texts(self) -> list[str]:
        return [i.key[2] for i in self.hidden()]


class HiddenItemsTest(HiddenFixtureCase):
    def test_skip_spellings_are_items_keyed_by_crate_file_text(self) -> None:
        for name, text in (
            ("spaced", SKIP_SPELLED),
            ("split", SKIP_SPLIT),
            ("commented", SKIP_COMMENTED),
            ("cfg_attr", SKIP_CFG_ATTR),
        ):
            with self.subTest(spelling=name):
                self.setUp()
                self.append_lib(text)
                found = self.hidden()
                self.assertIn((CRATE, LIB), {(i.key[0], i.key[1]) for i in found})
                self.assertTrue(all(i.target == CRATE for i in found))
                self.assertTrue(all(i.kind == "rust-hidden" for i in found))
                self.assertTrue(any("mutants" in i.key[2] for i in found))

    def test_macro_rules_is_an_item(self) -> None:
        self.append_lib(MACRO_RULES)
        self.assertIn("macro_rules ! m", self.texts())

    def test_each_hiding_expression_is_an_item(self) -> None:
        for name, text in INVOCATION_ITEMS.items():
            with self.subTest(item=name):
                self.setUp()
                self.append_lib(f"pub {text}")
                self.assertEqual(
                    len([t for t in self.texts() if not t.startswith("fn ")]), 1
                )

    def test_clean_cases_are_not_items(self) -> None:
        for name, text in INVOCATION_CLEAN.items():
            with self.subTest(clean=name):
                self.setUp()
                self.append_lib(f"pub {text}")
                self.assertEqual(self.hidden(), [])

    def test_prop_assert_in_cfg_test_module_is_not_an_item(self) -> None:
        self.append_lib(
            "#[cfg(test)]\nmod tests {\n    #[test]\n"
            "    fn t() { let x = 1; prop_assert!(x == 1 + 0); }\n}\n"
        )
        self.assertEqual(self.hidden(), [])

    def test_skip_mentioned_in_a_string_literal_is_not_an_item(self) -> None:
        self.append_lib('pub fn s() -> &\'static str {\n    "mutants::skip"\n}\n')
        self.assertEqual(self.hidden(), [])

    def test_new_function_with_a_mutant_is_not_an_item(self) -> None:
        self.append_lib('pub fn shout() {\n    println!("hi");\n}\n')
        self.assertEqual(self.hidden(), [])

    def test_new_mutantless_function_is_an_item(self) -> None:
        self.append_lib(
            "macro_rules! wrap { ($i:item) => { $i }; }\n"
            "wrap! { pub fn wrapped(a: u32) -> u32 { a * 2 } }\n"
        )
        self.assertIn("fn wrapped", self.texts())

    def test_skipped_new_function_is_both_a_skip_and_a_function_item(self) -> None:
        self.append_lib("#[mutants::skip]\npub fn z() -> u32 {\n    1\n}\n")
        texts = self.texts()
        self.assertIn("fn z", texts)
        self.assertIn("# [ mutants :: skip ]", texts)

    def test_untouched_crate_has_no_items(self) -> None:
        self.edit("README.md", "x\n")
        self.assertEqual(self.hidden(), [])

    def test_crate_rs_files_outside_src_are_scanned_except_test_trees(self) -> None:
        text = "fn t(a: u32) { assert_eq!(a + 1, 2); }\n"
        for rel, scanned in (
            ("build.rs", True),
            ("src/bin/x.rs", True),
            ("tests/x.rs", False),
            ("benches/b.rs", False),
            ("examples/e.rs", False),
        ):
            with self.subTest(file=rel):
                self.setUp()
                self.edit(rel, text)
                found = self.hidden()
                expected = [(rel, "assert_eq ! ( a + 1 , 2 )")] if scanned else []
                self.assertEqual([(i.key[1], i.key[2]) for i in found], expected)

    def test_new_function_rule_covers_src_only(self) -> None:
        self.edit("tests/probe.rs", "fn helper() -> u32 {\n    1\n}\n")
        self.assertEqual(self.hidden(), [])

    def test_include_of_a_file_outside_src_is_an_item(self) -> None:
        self.edit("extra.rs", "pub fn hidden(a: u32) -> u32 { a * 2 }\n")
        self.append_lib('include!("../extra.rs");\n')
        self.assertIn('include ! ( "../extra.rs" )', self.texts())

    def test_path_attribute_module_outside_src_is_an_item(self) -> None:
        self.edit("extra.rs", "pub fn hidden(a: u32) -> u32 { a * 2 }\n")
        self.append_lib('#[path = "../extra.rs"]\npub mod h;\n')
        self.assertIn('# [ path = "../extra.rs" ]', self.texts())

    def test_mask_decoy_does_not_hide_a_skip_end_to_end(self) -> None:
        self.append_lib(
            "mod m {\n    #![cfg(test)]\n}\n#[mutants::skip]\npub fn f() -> u32 {\n    1\n}\n"
        )
        texts = self.texts()
        self.assertIn("# [ mutants :: skip ]", texts)
        self.assertIn("fn f", texts)

    def test_methods_and_nested_functions_with_mutants_are_not_items(self) -> None:
        self.append_lib(
            "pub struct S;\nimpl S {\n    pub fn n(&self) -> u32 {\n        4\n    }\n}\n"
            "pub mod inner {\n    pub fn f() -> u32 {\n        5\n    }\n}\n"
        )
        self.assertEqual(self.hidden(), [])

    def test_deleted_source_file_yields_no_items(self) -> None:
        self.edit("src/extra.rs", "pub fn e() -> u32 {\n    dbg!(1 + 1)\n}\n")
        self.commit("add extra")
        self.base = self.rev("HEAD")
        (self.crate_path("src/extra.rs")).unlink()
        self.assertEqual(self.hidden(), [])

    def test_new_source_file_counts_every_occurrence(self) -> None:
        self.append_lib("mod extra;\n")
        self.edit("src/extra.rs", "pub fn e(a: u32) -> u32 {\n    dbg!(a + 1)\n}\n")
        self.assertEqual(self.texts(), ["dbg ! ( a + 1 )"])

    def test_listing_failure_is_a_marker_item(self) -> None:
        self.append_lib('pub fn shout() {\n    println!("hi");\n}\n')
        with mock.patch.object(mgi, "_list_mutants", return_value=None):
            found = self.hidden()
        self.assertEqual([i.key[1] for i in found], ["list-failed"])
        self.assertEqual(found[0].key[2], self.git("rev-parse", f"HEAD:{CRATE}"))


class MovedCodeTest(HiddenFixtureCase):
    def test_pure_move_of_an_existing_expression_is_not_an_item(self) -> None:
        self.append_lib(
            "pub fn first(a: u32, b: u32) -> u32 {\n    dbg!(a * b)\n}\n"
            "pub fn second() -> u32 {\n    1\n}\n"
        )
        self.commit("add")
        self.base = self.rev("HEAD")
        text = self.crate_path(LIB).read_text()
        moved = text.replace("    dbg!(a * b)\n", "    first(1, 2)\n").replace(
            "    1\n}\n", "    dbg!(a * b)\n}\n"
        )
        self.edit(
            LIB,
            moved.replace(
                "pub fn second() -> u32", "pub fn second(a: u32, b: u32) -> u32"
            ),
        )
        self.assertEqual(self.hidden(), [])

    def test_a_second_copy_of_an_existing_expression_is_an_item(self) -> None:
        self.append_lib("pub fn first(a: u32, b: u32) -> u32 {\n    dbg!(a * b)\n}\n")
        self.commit("add")
        self.base = self.rev("HEAD")
        self.append_lib("pub fn again(a: u32, b: u32) -> u32 {\n    dbg!(a * b)\n}\n")
        self.assertEqual(self.texts(), ["dbg ! ( a * b )"])


if __name__ == "__main__":
    unittest.main()
