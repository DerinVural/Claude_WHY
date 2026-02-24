"""Tests for FPGA vector operations."""

import pytest
from src.fpga.vector_ops import VectorOperations


class TestVectorOperations:
    """Tests for VectorOperations class."""

    def test_normalize_vector(self):
        """Test vector normalization."""
        ops = VectorOperations(use_fpga=False)
        vector = [3.0, 4.0]

        normalized = ops.normalize(vector)

        # Normalized vector should have unit length
        import math
        length = math.sqrt(sum(x**2 for x in normalized))
        assert abs(length - 1.0) < 1e-6

    def test_normalize_zero_vector(self):
        """Test normalization of zero vector."""
        ops = VectorOperations(use_fpga=False)
        vector = [0.0, 0.0, 0.0]

        normalized = ops.normalize(vector)

        assert normalized == vector

    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        ops = VectorOperations(use_fpga=False)
        vector = [1.0, 2.0, 3.0]

        similarity = ops.cosine_similarity(vector, vector)

        assert abs(similarity - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        ops = VectorOperations(use_fpga=False)
        vector_a = [1.0, 0.0]
        vector_b = [0.0, 1.0]

        similarity = ops.cosine_similarity(vector_a, vector_b)

        assert abs(similarity) < 1e-6

    def test_euclidean_distance(self):
        """Test Euclidean distance calculation."""
        ops = VectorOperations(use_fpga=False)
        vector_a = [0.0, 0.0]
        vector_b = [3.0, 4.0]

        distance = ops.euclidean_distance(vector_a, vector_b)

        assert abs(distance - 5.0) < 1e-6

    def test_find_top_k(self):
        """Test finding top-k similar vectors."""
        ops = VectorOperations(use_fpga=False)
        query = [1.0, 0.0, 0.0]
        vectors = [
            [1.0, 0.0, 0.0],  # Most similar
            [0.0, 1.0, 0.0],  # Orthogonal
            [0.5, 0.5, 0.0],  # Partially similar
            [-1.0, 0.0, 0.0], # Opposite
        ]

        results = ops.find_top_k(query, vectors, k=2)

        assert len(results) == 2
        assert results[0][0] == 0  # First should be the identical vector
        assert results[0][1] > results[1][1]  # Should be sorted by similarity
