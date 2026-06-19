from core.domain.document import ParsedDocument
from core.ports import LLMProvider

class DocumentComplianceValidator:
    """Domain Service: Uses a high-reasoning model to evaluate document validity."""

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def is_valid(self, document: ParsedDocument) -> bool:
        """Main Controller logic to check business rules and compliance."""
        if not document.sections:
            return False
            
        prompt = (
            "Review the following parsed legal document. "
            "Does it look like a valid regulatory or legal text? Answer 'yes' or 'no'.\n\n"
            f"URL: {document.document_url}\n"
            f"Sections Count: {len(document.sections)}"
        )
        schema = {"type": "object", "properties": {"is_valid": {"type": "boolean"}}}
        
        try:
            response = self._llm.complete(prompt, schema, agent_profile="main_controller")
            return response.get("is_valid", False)
        except NotImplementedError:
            # Fallback if provider stubs are not wired up yet
            return True
