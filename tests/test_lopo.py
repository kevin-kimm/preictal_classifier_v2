"""VT-08: patient separation checks. See docs/verification_plan.md."""

from preictal.evaluation.lopo import SubjectInfo, check_fold, full_split, inner_size, make_folds


def subjects():
    s = {f"chbmit:chb{i:02d}": SubjectInfo("chbmit", "train_test", i <= 21) for i in range(1, 24)}
    s.update({f"siena:PN{i:02d}": SubjectInfo("siena", "train_test", i < 4) for i in range(14)})
    s["tuh:aaaaaaac"] = SubjectInfo("tusz", "train_test", False)
    s["mental_arith:Subject00"] = SubjectInfo("mental_arith", "false_alarm_only", False)
    return s


def test_one_fold_per_eligible_test_patient():
    folds = make_folds(subjects(), ("chbmit", "siena"), seed=0)
    assert len(folds) == 25
    assert sorted(f.test for f in folds) == sorted(s for s, i in subjects().items()
                                                   if i.eligible_test_patient)


def test_no_leakage_in_any_fold_or_seed():
    for seed in range(5):
        for f in make_folds(subjects(), ("chbmit", "siena"), seed):
            assert check_fold(f) == []
            assert f.test not in f.train and f.test not in f.inner
            assert not set(f.inner) & set(f.train)


def test_training_uses_every_other_train_test_subject_of_the_datasets():
    f = make_folds(subjects(), ("chbmit", "siena"), seed=0)[0]
    assert len(f.train) + len(f.inner) + 1 == 23 + 14
    assert not any(s.startswith(("tuh:", "mental_arith:")) for s in f.train + f.inner)


def test_inner_set_size_and_eligibility():
    assert inner_size(24) == 5 and inner_size(3) == 2 and inner_size(1) == 1
    for f in make_folds(subjects(), ("chbmit", "siena"), seed=3):
        assert len(f.inner) == 5
        assert all(subjects()[s].eligible_test_patient for s in f.inner)


def test_folds_are_reproducible_and_depend_on_seed():
    a = make_folds(subjects(), ("chbmit", "siena"), seed=1)
    assert a == make_folds(subjects(), ("chbmit", "siena"), seed=1)
    assert a != make_folds(subjects(), ("chbmit", "siena"), seed=2)


def test_full_split_has_no_test_patient():
    f = full_split(subjects(), ("chbmit", "siena"), seed=0)
    assert f.test == "" and check_fold(f) == [] and len(f.inner) == 5


def test_leakage_is_detected():
    from preictal.evaluation.lopo import Fold
    bad = Fold(0, "chbmit:chb01", ("chbmit:chb02",), ("chbmit:chb01", "chbmit:chb02"))
    assert len(check_fold(bad)) == 2
