import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ReferenceLookupTests(unittest.TestCase):
    def test_doi_lookup_prefers_pubmed_before_crossref_or_openalex(self):
        import reference_lookup

        calls = []

        def fake_fetch_json(url, params=None, headers=None, timeout=20):
            if "esearch.fcgi" in url:
                calls.append("ncbi_search")
                return {"esearchresult": {"idlist": ["12345678"]}}
            if "esummary.fcgi" in url:
                calls.append("ncbi_summary")
                return {
                    "result": {
                        "uids": ["12345678"],
                        "12345678": {
                            "uid": "12345678",
                            "title": "Example cardiovascular trial",
                            "fulljournalname": "Journal of Examples",
                            "pubdate": "2024 Jan",
                            "authors": [{"name": "Smith J"}, {"name": "Tan A"}],
                            "articleids": [
                                {"idtype": "pubmed", "value": "12345678"},
                                {"idtype": "doi", "value": "10.1000/example"},
                            ],
                        },
                    }
                }
            self.fail(f"unexpected HTTP call: {url}")

        result = reference_lookup.lookup_reference(
            doi="10.1000/example",
            fetch_json=fake_fetch_json,
        )

        self.assertEqual(result["source_method"], "ncbi_eutilities")
        self.assertEqual(result["pmid"], "12345678")
        self.assertEqual(result["doi"], "10.1000/example")
        self.assertEqual(result["first_author"], "Smith")
        self.assertEqual(calls, ["ncbi_search", "ncbi_summary"])

    def test_doi_lookup_uses_crossref_when_pubmed_has_no_match(self):
        import reference_lookup

        calls = []

        def fake_fetch_json(url, params=None, headers=None, timeout=20):
            if "esearch.fcgi" in url:
                calls.append("ncbi_search")
                return {"esearchresult": {"idlist": []}}
            if "api.crossref.org" in url:
                calls.append("crossref")
                return {
                    "message": {
                        "DOI": "10.2000/crossref",
                        "title": ["Crossref-only article"],
                        "container-title": ["Metadata Journal"],
                        "author": [{"family": "Jones", "given": "B"}],
                        "published-print": {"date-parts": [[2021, 5, 1]]},
                    }
                }
            self.fail(f"unexpected HTTP call: {url}")

        result = reference_lookup.lookup_reference(
            doi="10.2000/crossref",
            fetch_json=fake_fetch_json,
        )

        self.assertEqual(result["source_method"], "crossref_lookup")
        self.assertEqual(result["doi"], "10.2000/crossref")
        self.assertEqual(result["title"], "Crossref-only article")
        self.assertEqual(result["first_author"], "Jones")
        self.assertEqual(calls, ["ncbi_search", "crossref"])

    def test_title_lookup_uses_openalex_after_pubmed_and_crossref_fail(self):
        import reference_lookup

        calls = []

        def fake_fetch_json(url, params=None, headers=None, timeout=20):
            if "esearch.fcgi" in url:
                calls.append("ncbi_search")
                return {"esearchresult": {"idlist": []}}
            if "api.crossref.org" in url:
                calls.append("crossref")
                return {"message": {"items": []}}
            if "api.openalex.org" in url:
                calls.append("openalex")
                return {
                    "results": [
                        {
                            "title": "Recovered title from OpenAlex",
                            "doi": "https://doi.org/10.3000/openalex",
                            "publication_year": 2020,
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Journal"}
                            },
                            "authorships": [
                                {"author": {"display_name": "Ng C"}}
                            ],
                            "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/98765432/"},
                        }
                    ]
                }
            self.fail(f"unexpected HTTP call: {url}")

        result = reference_lookup.lookup_reference(
            title="Recovered title",
            author="Ng",
            year="2020",
            fetch_json=fake_fetch_json,
        )

        self.assertEqual(result["source_method"], "openalex_lookup")
        self.assertEqual(result["doi"], "10.3000/openalex")
        self.assertEqual(result["pmid"], "98765432")
        self.assertEqual(result["journal"], "OpenAlex Journal")
        self.assertEqual(calls, ["ncbi_search", "crossref", "openalex"])


if __name__ == "__main__":
    unittest.main()
