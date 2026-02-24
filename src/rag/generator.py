"""Response generator using Vertex AI LLM."""

from typing import List, Dict, Any, Optional
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, Part


class ResponseGenerator:
    """Generates responses using Vertex AI Generative Models."""

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model_name: str = "gemini-1.5-flash",
    ):
        """Initialize the response generator.

        Args:
            project_id: GCP project ID
            location: GCP region for Vertex AI
            model_name: Name of the generative model to use
        """
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def generate(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response based on query and context.

        Args:
            query: User query
            context_documents: Retrieved documents for context
            system_prompt: Optional system prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens in response

        Returns:
            Generated response text
        """
        # Build context from documents
        context = "\n\n".join(
            f"Document {i+1}:\n{doc['content']}"
            for i, doc in enumerate(context_documents)
        )

        # Build prompt
        prompt = f"""Based on the following context, answer the user's question.

Context:
{context}

Question: {query}

Answer:"""

        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"

        # Generate response
        response = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )

        return response.text
