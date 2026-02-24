"""Vector operations optimized for FPGA acceleration."""

from typing import List, Tuple
import numpy as np
from .accelerator import FPGAAccelerator


class VectorOperations:
    """High-level vector operations with optional FPGA acceleration."""

    def __init__(self, use_fpga: bool = False, fpga_accelerator: FPGAAccelerator = None):
        """Initialize vector operations.

        Args:
            use_fpga: Whether to use FPGA acceleration
            fpga_accelerator: Optional FPGA accelerator instance
        """
        self.use_fpga = use_fpga
        self.accelerator = fpga_accelerator

        if use_fpga and fpga_accelerator is None:
            self.accelerator = FPGAAccelerator()
            self.accelerator.initialize()

    def normalize(self, vector: List[float]) -> List[float]:
        """Normalize a vector to unit length.

        Args:
            vector: Input vector

        Returns:
            Normalized vector
        """
        v = np.array(vector)
        norm = np.linalg.norm(v)
        if norm == 0:
            return vector
        return (v / norm).tolist()

    def cosine_similarity(
        self, vector_a: List[float], vector_b: List[float]
    ) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vector_a: First vector
            vector_b: Second vector

        Returns:
            Cosine similarity score
        """
        if self.use_fpga and self.accelerator:
            return self.accelerator.accelerate_cosine_similarity(vector_a, vector_b)

        a = np.array(vector_a)
        b = np.array(vector_b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def euclidean_distance(
        self, vector_a: List[float], vector_b: List[float]
    ) -> float:
        """Compute Euclidean distance between two vectors.

        Args:
            vector_a: First vector
            vector_b: Second vector

        Returns:
            Euclidean distance
        """
        a = np.array(vector_a)
        b = np.array(vector_b)
        return float(np.linalg.norm(a - b))

    def find_top_k(
        self,
        query_vector: List[float],
        vectors: List[List[float]],
        k: int = 5,
    ) -> List[Tuple[int, float]]:
        """Find top-k most similar vectors.

        Args:
            query_vector: Query vector
            vectors: List of vectors to search
            k: Number of top results to return

        Returns:
            List of (index, similarity) tuples
        """
        if self.use_fpga and self.accelerator:
            similarities = self.accelerator.batch_cosine_similarity(
                query_vector, vectors
            )
        else:
            similarities = [
                self.cosine_similarity(query_vector, v) for v in vectors
            ]

        # Get top-k indices
        indexed_similarities = list(enumerate(similarities))
        indexed_similarities.sort(key=lambda x: x[1], reverse=True)

        return indexed_similarities[:k]
