from zetarix.domain.document import ParsedDocument
from zetarix.ports import DocumentExtractorPort
from zetarix.validation.document_validator import DocumentComplianceValidator

class ScraperOrchestrator:
    """Main Controller: Orchestrates web scraping using abstraction ports."""

    def __init__(self, extractor: DocumentExtractorPort, validator: DocumentComplianceValidator):
        self._extractor = extractor
        self._validator = validator

    def scrape_and_validate(self, urls: list[str]) -> list[ParsedDocument]:
        """
        Orchestrates scraping of URLs. The pipeline delegates heavy parsing 
        to small sub-agents behind the DocumentExtractorPort, keeping this 
        main controller's context clean.
        """
        results = []
        for url in urls:
            parsed_document = self._extractor.scrape_url(url)
            
            # The validator uses the main_controller profile for business logic.
            if self._validator.is_valid(parsed_document):
                results.append(parsed_document)
                
        return results
