import logging

from Bio import Entrez, Medline

from config import BIO_EMAIL

logger = logging.getLogger(__name__)


class PubMedClient:
    def __init__(self):
        Entrez.email = BIO_EMAIL

    def fetch_pubmed(self, pubmed_input: dict, limit: int = 5) -> list[dict]:
        query = pubmed_input.get("primary_query", "")
        if not query:
            return []

        if pubmed_input.get("filters"):
            filter_tags = [f"{f}[Filter]" for f in pubmed_input["filters"]]
            query = f"({query}) AND ({' OR '.join(filter_tags)})"

        try:
            handle = Entrez.esearch(db="pubmed", term=query, retmax=limit)
            record = Entrez.read(handle)
            handle.close()
            id_list = record["IdList"]

            if not id_list and pubmed_input.get("fallback_query"):
                logger.info("No results for primary query, trying fallback")
                return self.fetch_pubmed({"primary_query": pubmed_input["fallback_query"]}, limit)

            if not id_list:
                return []

            handle = Entrez.efetch(db="pubmed", id=id_list, rettype="medline", retmode="text")
            records = list(Medline.parse(handle))
            handle.close()

            return [
                {
                    "id": r.get("PMID"),
                    "title": r.get("TI"),
                    "source": r.get("JT"),
                    "pub_date": r.get("DP"),
                    "abstract": r.get("AB", "No abstract available."),
                    "pub_types": r.get("PT", []),
                    "authors": r.get("AU", []),
                }
                for r in records
            ]
        except Exception as e:
            logger.error("PubMed fetch failed: %s", e)
            return [{"error": str(e)}]

    def fetch_ncbi_books(self, query: str, limit: int = 4) -> list[dict]:
        """Search NCBI Bookshelf for clinical guideline chapters."""
        if not query:
            return []
        try:
            handle = Entrez.esearch(db="books", term=query, retmax=limit)
            record = Entrez.read(handle)
            handle.close()
            ids = record.get("IdList", [])
            if not ids:
                return []
            handle = Entrez.esummary(db="books", id=ids)
            summaries = Entrez.read(handle)
            handle.close()
            results = []
            for doc in summaries:
                results.append({
                    "id": str(doc.get("Id", "")),
                    "title": str(doc.get("Title", "")),
                    "book": str(doc.get("BookName", "")),
                    "abstract": str(doc.get("Summary", "")),
                    "source": "NCBI Bookshelf",
                    "pub_types": ["Guideline"],
                })
            return results
        except Exception as e:
            logger.warning("NCBI Books fetch failed: %s", e)
            return []
