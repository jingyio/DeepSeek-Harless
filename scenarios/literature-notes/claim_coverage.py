"""Necessary literal checks for technical names; never an entailment classifier."""
import re


def technical_name_gaps(statement, quotes):
    # Acronyms/camel-case names only. Do not guess English title words, translate
    # Chinese propositions or infer a benchmark from a page-level mention.
    names = re.findall(r'(?<![A-Za-z])(?:[A-Z]{3,}[A-Za-z0-9]*|[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]*)+)', statement)
    def compact(value):
        return re.sub(r'[^a-z0-9]', '', value.casefold())
    sources = [compact(q) for q in quotes]
    return sorted({name for name in names if not any(compact(name) in source for source in sources)})
