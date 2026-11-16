"""KEGG module completeness (phase 2, A9)."""

import pytest

from pankegg import resource_path
from pankegg.modules import ModuleSet, load_modules, parse

GLYCOLYSIS = ("(K00844,K12407,K00845,K25026,K00886,K08074,K00918) (K01810,K06859,K13810,K15916) "
              "(K00850,K16370,K21071,K24182,K00918) (K01623,K01624,K11645,K16305,K16306) K01803 "
              "(((K00134,K00150) K00927),K11389) (K01834,K15633,K15634,K15635) (K01689,K27394) (K00873,K12406)")


def one(definition, kos, others=None):
    mods = {"M99999": ("test", definition), **(others or {})}
    return ModuleSet(mods).completeness(kos).get("M99999")


def test_steps_and_alternatives():
    assert len(parse(GLYCOLYSIS)) == 9
    full = ["K00844", "K01810", "K00850", "K01623", "K01803", "K00134", "K00927", "K01834", "K01689", "K00873"]
    assert one(GLYCOLYSIS, full) == (9, 9, 100.0)
    assert one(GLYCOLYSIS, full[1:]) == (8, 9, 88.89)           # first step missing
    # step 6 is ((K00134 or K00150) then K00927) or K11389: half of the route, or the alternative
    without = [k for k in full if k != "K00927"]
    assert one(GLYCOLYSIS, without) == (8, 9, round(100 * 8.5 / 9, 2))
    assert one(GLYCOLYSIS, without + ["K11389"]) == (9, 9, 100.0)
    assert one(GLYCOLYSIS, []) is None and one(GLYCOLYSIS, ["K99999"]) is None


@pytest.mark.parametrize("definition, kos, expected", [
    ("K00001+K00002", ["K00001", "K00002"], (1, 1, 100.0)),             # complex: all subunits
    ("K00001+K00002", ["K00001"], (0, 1, 50.0)),
    ("K00001+K00002-K00003", ["K00001", "K00002"], (1, 1, 100.0)),      # optional subunit ignored
    ("K00001 -K00003 K00002", ["K00001", "K00002"], (2, 2, 100.0)),     # optional step ignored
    ("K00001 -- K00002", ["K00001", "K00002"], (2, 2, 100.0)),          # step without a KO ignored
    ("K00001,K00002,K00003", ["K00003"], (1, 1, 100.0)),                # top-level alternatives: one step
    ("(K00001 K00002,K00003) K00004", ["K00003"], (1, 2, 50.0)),
    ("(K00001,K00002)+K00003 K00004", ["K00002", "K00003"], (1, 2, 50.0)),
    ("K00001-(K00002,K00003)", ["K00001"], (1, 1, 100.0)),
])
def test_definition_syntax(definition, kos, expected):
    assert one(definition, kos) == expected


def test_module_references():
    others = {"M00001": ("a", "K00001 K00002"), "M00002": ("b", "K00003")}
    assert one("(M00001,M00002) K00004", ["K00003", "K00004"], others) == (2, 2, 100.0)
    assert one("M00001 K00004", ["K00001", "K00004"], others) == (1, 2, 75.0)
    assert one("M99999", ["K00001"]) is None                                 # circular: never satisfied


def test_every_shipped_definition_parses():
    modules = load_modules(resource_path("data", "kegg_modules.tsv"))
    assert len(modules) > 400 and modules["M00001"][1] == GLYCOLYSIS
    mset = ModuleSet(modules)
    unparsed = [m for m, steps in mset.steps.items() if not steps]
    assert unparsed == [], unparsed
    everything = set().union(*mset.kos.values())
    result = mset.completeness(everything)
    incomplete = [m for m in modules if result.get(m, (0, 0, 0))[2] != 100.0]
    assert incomplete == [], f"with every KO present every module must be complete: {incomplete[:5]}"
