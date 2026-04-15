"""Vector Utilities - 向量工具函数

提供向量计算、相似度度量等工具函数
"""

import numpy as np
from typing import List, Optional


def normalize(vector: np.ndarray) -> np.ndarray:
    """
    向量归一化

    Args:
        vector: 输入向量

    Returns:
        归一化后的向量
    """
    norm = np.linalg.norm(vector)
    if norm < 1e-10:
        return vector
    return vector / norm


def normalize_list(vector: List[float]) -> List[float]:
    """
    向量归一化 (List 版本)

    Args:
        vector: 输入向量列表

    Returns:
        归一化后的向量列表
    """
    arr = np.array(vector)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return vector
    return (arr / norm).tolist()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    余弦相似度

    Args:
        a: 向量 a
        b: 向量 b

    Returns:
        余弦相似度 (-1 到 1)
    """
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def cosine_similarity_list(a: List[float], b: List[float]) -> float:
    """
    余弦相似度 (List 版本)
    """
    arr_a = np.array(a)
    arr_b = np.array(b)
    return cosine_similarity(arr_a, arr_b)


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    欧氏距离

    Args:
        a: 向量 a
        b: 向量 b

    Returns:
        欧氏距离
    """
    return float(np.linalg.norm(a - b))


def euclidean_distance_list(a: List[float], b: List[float]) -> float:
    """
    欧氏距离 (List 版本)
    """
    return float(np.linalg.norm(np.array(a) - np.array(b)))


def dot_product(a: np.ndarray, b: np.ndarray) -> float:
    """
    点积

    Args:
        a: 向量 a
        b: 向量 b

    Returns:
        点积结果
    """
    return float(np.dot(a, b))


def dot_product_list(a: List[float], b: List[float]) -> float:
    """
    点积 (List 版本)
    """
    return float(np.dot(np.array(a), np.array(b)))


def manhattan_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    曼哈顿距离

    Args:
        a: 向量 a
        b: 向量 b

    Returns:
        曼哈顿距离
    """
    return float(np.sum(np.abs(a - b)))


def manhattan_distance_list(a: List[float], b: List[float]) -> float:
    """
    曼哈顿距离 (List 版本)
    """
    return float(np.sum(np.abs(np.array(a) - np.array(b))))


def batch_normalize(vectors: List[np.ndarray]) -> List[np.ndarray]:
    """
    批量归一化

    Args:
        vectors: 向量列表

    Returns:
        归一化后的向量列表
    """
    return [normalize(v) for v in vectors]


def compute_centroid(vectors: List[np.ndarray]) -> np.ndarray:
    """
    计算质心

    Args:
        vectors: 向量列表

    Returns:
        质心向量
    """
    if not vectors:
        return np.array([])
    return np.mean(vectors, axis=0)


def compute_centroid_list(vectors: List[List[float]]) -> List[float]:
    """
    计算质心 (List 版本)
    """
    if not vectors:
        return []
    return compute_centroid(np.array(vectors)).tolist()


def batch_cosine_similarity(
    query: np.ndarray, candidates: List[np.ndarray]
) -> List[float]:
    """
    批量计算余弦相似度

    Args:
        query: 查询向量
        candidates: 候选向量列表

    Returns:
        相似度列表
    """
    query_norm = normalize(query)
    results = []

    for candidate in candidates:
        candidate_norm = normalize(candidate)
        sim = cosine_similarity(query_norm, candidate_norm)
        results.append(sim)

    return results


def batch_cosine_similarity_list(
    query: List[float], candidates: List[List[float]]
) -> List[float]:
    """
    批量计算余弦相似度 (List 版本)
    """
    query_arr = np.array(query)
    candidate_arrs = np.array(candidates)
    return batch_cosine_similarity(query_arr, candidate_arrs).tolist()
