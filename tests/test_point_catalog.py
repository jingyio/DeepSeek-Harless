"""Large source catalogs must preserve coverage within the planning budget."""

from __future__ import annotations

import json
import unittest

from src.adapters.point_research_semantic import prepare_point_queries


class PointCatalogTests(unittest.TestCase):
    def test_sixteen_sources_are_retained_and_late_method_survives(self) -> None:
        points = [{"id": "pose", "requirement": "比较 3DGS 位姿估计和精优化方法"}]
        pages = []
        for index in range(16):
            topic = "3DGS 位姿估计方法采用几何约束进行精优化。" if index == 9 else "普通资料介绍背景。"
            pages.append({"source": f"web-{index:02}.txt", "page": 1,
                          "text": f"Benchmark snapshot title: item {index}\n" + "广告和导航" * 90 + topic})
        prompt = prepare_point_queries("研究 3DGS 重定位", points, pages)
        catalog = json.loads(prompt.split("Source catalog (every source retained; excerpts are sampled, not complete): ", 1)[1])
        self.assertLessEqual(len(prompt), 8_000)
        self.assertEqual(len(catalog), 16)
        self.assertIn("几何约束", next(row for row in catalog if row["source"] == "web-09.txt")["relevant_excerpt"])


if __name__ == "__main__":
    unittest.main()
