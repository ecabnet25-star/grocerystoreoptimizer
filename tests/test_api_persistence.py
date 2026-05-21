import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from grocery_optimizer.api.schemas import CreateUserRequest, OptimizeRequest, SavePlanRequest
from grocery_optimizer.api.users import (
    create_user_profile_with_db,
    delete_saved_plan_with_db,
    get_saved_plan_with_db,
    get_saved_plans_paginated_with_db,
    get_saved_plans_with_db,
    logout_user_with_db,
    refresh_user_token_with_db,
    rename_saved_plan_with_db,
    save_optimized_plan_with_db,
)


class TestApiPersistence(unittest.TestCase):
    def test_create_user_save_and_list_plan(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test.db")

            user = create_user_profile_with_db(
                CreateUserRequest(name="Ethan", email="ethan@example.com", password="Password123"),
                db_path=db_path,
            )
            user_id = user["user"]["id"]
            auth_token = user["auth_token"]

            save_result = save_optimized_plan_with_db(
                user_id=user_id,
                request=SavePlanRequest(
                    label="Weekly Montreal Plan",
                    optimize_request=OptimizeRequest(
                        budget=45,
                        max_items=7,
                        strategy="knapsack",
                        required_categories=["produce", "protein"],
                        excluded_categories=["dairy"],
                        location="montreal",
                    ),
                ),
                db_path=db_path,
                auth_token=auth_token,
            )

            self.assertIn("saved", save_result)
            self.assertIn("result", save_result)

            plans = get_saved_plans_with_db(user_id, db_path=db_path, auth_token=auth_token)
            self.assertEqual(plans["user"]["email"], "ethan@example.com")
            self.assertEqual(len(plans["plans"]), 1)
            self.assertEqual(plans["plans"][0]["label"], "Weekly Montreal Plan")
            self.assertEqual(plans["plans"][0]["request"]["optimize_request"]["strategy"], "knapsack")
            self.assertIn("include_live_pricing", plans["plans"][0]["request"]["optimize_request"])

            deleted = delete_saved_plan_with_db(
                user_id=user_id,
                plan_id=save_result["saved"]["id"],
                auth_token=auth_token,
                db_path=db_path,
            )
            self.assertTrue(deleted["deleted"])

            plans_after_delete = get_saved_plans_with_db(user_id, db_path=db_path, auth_token=auth_token)
            self.assertEqual(len(plans_after_delete["plans"]), 0)

    def test_refresh_and_logout_tokens(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "auth.db")

            user = create_user_profile_with_db(
                CreateUserRequest(name="Ethan", email="ethan+auth@example.com", password="Password123"),
                db_path=db_path,
            )
            user_id = user["user"]["id"]
            token = user["auth_token"]

            refreshed = refresh_user_token_with_db(user_id=user_id, auth_token=token, db_path=db_path)
            new_token = refreshed["auth_token"]

            with self.assertRaises(ValueError):
                get_saved_plans_with_db(user_id, db_path=db_path, auth_token=token)

            logout_result = logout_user_with_db(user_id=user_id, auth_token=new_token, db_path=db_path)
            self.assertTrue(logout_result["revoked"])

            with self.assertRaises(ValueError):
                get_saved_plans_with_db(user_id, db_path=db_path, auth_token=new_token)

    def test_paginated_and_single_plan_read(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "page.db")
            user = create_user_profile_with_db(
                CreateUserRequest(name="Paged", email="paged@example.com", password="Password123"),
                db_path=db_path,
            )
            user_id = user["user"]["id"]
            token = user["auth_token"]

            saved = save_optimized_plan_with_db(
                user_id=user_id,
                request=SavePlanRequest(
                    label="Paged Plan",
                    optimize_request=OptimizeRequest(location="montreal", budget=33),
                ),
                db_path=db_path,
                auth_token=token,
            )

            page = get_saved_plans_paginated_with_db(
                user_id=user_id,
                db_path=db_path,
                auth_token=token,
                limit=1,
                offset=0,
            )
            self.assertEqual(page["pagination"]["limit"], 1)
            self.assertGreaterEqual(page["pagination"]["total"], 1)
            self.assertGreaterEqual(len(page["plans"]), 1)

            plan_id = saved["saved"]["id"]
            single = get_saved_plan_with_db(
                user_id=user_id,
                plan_id=plan_id,
                auth_token=token,
                db_path=db_path,
            )
            self.assertEqual(single["plan"]["id"], plan_id)

            renamed = rename_saved_plan_with_db(
                user_id=user_id,
                plan_id=plan_id,
                label="Paged Plan Renamed",
                auth_token=token,
                db_path=db_path,
            )
            self.assertTrue(renamed["updated"])

            renamed_plan = get_saved_plan_with_db(
                user_id=user_id,
                plan_id=plan_id,
                auth_token=token,
                db_path=db_path,
            )
            self.assertEqual(renamed_plan["plan"]["label"], "Paged Plan Renamed")

            with self.assertRaises(ValueError):
                get_saved_plans_paginated_with_db(
                    user_id=user_id,
                    db_path=db_path,
                    auth_token=token,
                    limit=0,
                    offset=0,
                )


if __name__ == "__main__":
    unittest.main()
