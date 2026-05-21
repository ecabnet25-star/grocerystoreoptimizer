import unittest

from grocery_optimizer.cli import build_parser


class TestMain(unittest.TestCase):
    def test_parser_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.budget, 50.0)
        self.assertEqual(args.max_items, 10)
        self.assertEqual(args.strategy, "greedy")
        self.assertEqual(args.excluded_categories, [])
        self.assertEqual(args.nutrition_weight, 1.0)


if __name__ == "__main__":
    unittest.main()
