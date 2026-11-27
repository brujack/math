"""One-mutant canary module: cosmic-ray's only mutant is ReplaceTrueWithFalse in ok()."""


def ok():
    return True


def label():
    return "new"
