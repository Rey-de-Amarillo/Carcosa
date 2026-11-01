import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bot
from scripts import download_history


class FakeProvider:
    def __init__(self, fail=None):
        self.requests = []
        self.fail = fail
        self.catalog = [{"key":key,"active":True,"has_outrights":False} for key in bot.WATCHLIST]
        self.catalog += [{"key":f"sport_{index:02d}","active":True,"has_outrights":False} for index in range(24)]
        self.catalog += [{"key":"inactive","active":False,"has_outrights":False},
                         {"key":"future_winner","active":True,"has_outrights":True}]

    def status(self):
        return {"configured":True,"local_monthly_limit":450}

    def sports(self,force=False):
        return {"payload":self.catalog}

    def odds(self,**arguments):
        self.requests.append(arguments)
        if arguments["sport"] == self.fail:
            raise ValueError("private URL contains apiKey=DO_NOT_PRINT_THIS_SECRET")
        return {"payload":[],"cached":False}


class BotCycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.report_path = self.root / "app/data/report.json"
        bot.atomic_json(self.report_path,{"meta":{"generated_at":"historical-replay-time"},
                                          "backtest":{"preserve":"historical calculations"},
                                          "history_export":{"count":23940,"sha256":"unchanged"}})
        self.clock = datetime(2026,10,30,12,tzinfo=timezone.utc)
        self.logs = []
        self.scans = []

    def scan(self,output=None):
        self.scans.append(output)
        return {"scan_id":str(len(self.scans)),"generated_at":self.clock.isoformat(),"opportunities":[],
                "quotes":0,"quote_events":0,"execution_enabled":False}

    def cycle(self,provider,**arguments):
        return bot.run_once(root=self.root,provider=provider,now=arguments.pop("now",self.clock),
                            scan_fn=self.scan,audit_fn=lambda action,payload:self.logs.append((action,payload)),
                            cache_fn=lambda key:None,**arguments)

    def test_fixed_priorities_rotation_and_no_outrights(self):
        provider=FakeProvider()
        first=bot.select_sports(provider.catalog,self.clock.date())
        second=bot.select_sports(provider.catalog,(self.clock+timedelta(days=1)).date())
        self.assertEqual(first[:4],list(bot.WATCHLIST))
        self.assertEqual(len(first),12)
        self.assertEqual(len(set(first)),12)
        self.assertNotIn("inactive",first)
        self.assertNotIn("future_winner",first)
        self.assertNotEqual(first[4:],second[4:])

    def test_restarts_do_not_spend_second_daily_batch_and_preserve_backtest(self):
        provider=FakeProvider()
        first=self.cycle(provider,refresh_fn=lambda *args:self.fail("Unexpected historical refresh"))
        self.assertEqual(len(provider.requests),12)
        self.assertTrue(all(r["markets"]=="h2h" and r["regions"]=="eu" and not r["force"] for r in provider.requests))
        second=self.cycle(provider)
        self.assertEqual(len(provider.requests),12)
        self.assertEqual(second["new_snapshots"],0)
        self.assertEqual(len(self.scans),2)
        report=bot.read_json(self.report_path)
        self.assertEqual(report["backtest"],{"preserve":"historical calculations"})
        self.assertEqual(report["history_export"],{"count":23940,"sha256":"unchanged"})
        self.assertEqual(report["meta"]["generated_at"],"historical-replay-time")
        self.assertEqual(report["live"]["scan_id"],"2")
        self.assertFalse(first["execution_enabled"])

    def test_partial_network_failure_is_reserved_and_never_leaks_secret(self):
        provider=FakeProvider(fail=bot.WATCHLIST[0])
        result=self.cycle(provider)
        self.assertEqual(len(provider.requests),12)
        self.assertEqual(result["new_snapshots"],11)
        self.assertEqual(result["errors"][0]["type"],"ValueError")
        self.assertEqual(len(self.scans),1)
        self.cycle(provider)
        self.assertEqual(len(provider.requests),12)
        combined=json.dumps([result,self.logs,bot.read_json(self.root/"data/runtime/bot_state.json")])
        self.assertNotIn("DO_NOT_PRINT_THIS_SECRET",combined)
        self.assertNotIn("apiKey",combined)

    def test_refresh_is_explicit_and_at_most_once_per_utc_date(self):
        provider=FakeProvider(); refreshed=[]
        def refresh(root,day):
            refreshed.append((root,day))
            return {"status":"completed","matches_changed":False,"backtest_rebuilt":False}
        self.cycle(provider,refresh_fn=refresh)
        self.assertEqual(refreshed,[])
        self.cycle(provider,refresh_data=True,refresh_fn=refresh)
        self.cycle(provider,refresh_data=True,refresh_fn=refresh)
        self.assertEqual(len(refreshed),1)
        self.cycle(provider,now=self.clock+timedelta(days=1),refresh_data=True,refresh_fn=refresh)
        self.assertEqual(len(refreshed),2)
        self.assertEqual(len(provider.requests),24)

    def test_single_instance_kernel_lock(self):
        lock=self.root/"bot.lock"
        with bot.single_instance(lock):
            with self.assertRaises(RuntimeError):
                with bot.single_instance(lock):
                    self.fail("A second instance acquired the same lock")
        with bot.single_instance(lock):
            pass

    def test_watch_rejects_an_interval_below_24_hours_without_starting(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            bot.main(["--watch","--interval-hours","1"])
        self.assertEqual(raised.exception.code,2)


class HistoryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.matches=self.root/"data/processed/matches.csv"
        self.matches.parent.mkdir(parents=True)
        self.matches.write_text("old coherent normalized history")
        bot.atomic_json(self.root/"app/data/report.json",{"old":"coherent report"})
        bot.atomic_json(self.root/"data/manifest.json",{"files":[],"derived":{"old":True}})
        self.fake_downloader=SimpleNamespace(records={},errors=[])
        self.calls=[]

    def run_refresh(self,change=False,fail_stage=None):
        def runner(command,**arguments):
            stage=Path(command[1]).name
            self.calls.append((stage,command[2:]))
            if stage=="download_history.py" and change:
                self.matches.write_text("new normalized history")
            return SimpleNamespace(returncode=2 if stage==fail_stage else 0)
        with (patch.object(download_history,"Downloader",return_value=self.fake_downloader) as constructor,
              patch.object(download_history,"download_football") as download):
            result=bot.refresh_histories(self.root,date(2026,10,30),runner=runner)
            constructor.assert_called_once_with(refresh=True)
            download.assert_called_once_with(self.fake_downloader,first_year=2026,last_year=2026)
        return result

    def test_unchanged_history_does_not_recompute_backtest(self):
        original_leagues=download_history.LEAGUES
        result=self.run_refresh(change=False)
        self.assertFalse(result["matches_changed"])
        self.assertFalse(result["backtest_rebuilt"])
        self.assertEqual([x[0] for x in self.calls],["download_history.py","download_us_sports.py"])
        self.assertEqual(self.calls[0][1],["--skip-events","--last-year","2026"])
        self.assertIs(download_history.LEAGUES,original_leagues)

    def test_changed_history_rebuilds_after_cached_us_sports(self):
        result=self.run_refresh(change=True)
        self.assertTrue(result["matches_changed"])
        self.assertTrue(result["backtest_rebuilt"])
        self.assertEqual([x[0] for x in self.calls],
                         ["download_history.py","download_us_sports.py","build_report.py"])
        self.assertTrue(all("--refresh" not in arguments for _,arguments in self.calls))

    def test_partial_pipeline_failure_restores_the_coherent_history(self):
        with self.assertRaises(RuntimeError):
            self.run_refresh(change=True,fail_stage="download_us_sports.py")
        self.assertEqual(self.matches.read_text(),"old coherent normalized history")
        self.assertEqual(bot.read_json(self.root/"app/data/report.json"),{"old":"coherent report"})

    def test_v2_failure_restores_derived_cohort_but_preserves_immutable_registry_and_sqlite(self):
        derived = ["app/data/report.json", "app/data/research.json",
                   "data/analysis/research_v2.json", "data/analysis/selection_v2.json",
                   "data/analysis/integration_v2.jsonl", "data/analysis/portfolio_v2.json",
                   "config/selected_model_v2.json", "data/runtime/prospective_v2.json"]
        old_hash, new_hash = "a"*64, "b"*64
        original = {}
        for name in derived:
            path = self.root/name
            bot.atomic_json(path, {"cohort":"old", "model_hash":old_hash, "events":17})
            original[path] = path.read_bytes()
        manifest = self.root/"data/manifest.json"
        original[manifest] = manifest.read_bytes()
        original[self.matches] = self.matches.read_bytes()

        existing_registry = self.root/f"data/runtime/prospective/{old_hash}.json"
        new_registry = self.root/f"data/runtime/prospective/{new_hash}.json"
        bot.atomic_json(existing_registry, {"model_hash":old_hash, "events":17})
        existing_registry_bytes = existing_registry.read_bytes()
        database = self.root/"data/runtime/kraken.sqlite3"
        connection = sqlite3.connect(database)
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, event TEXT)")
        connection.execute("INSERT INTO audit(event) VALUES ('before refresh')")
        connection.commit()

        with self.assertRaisesRegex(RuntimeError, "forced v2 stage failure"):
            with bot.preserve_normalized_outputs(self.root):
                for name in derived:
                    bot.atomic_json(self.root/name, {"cohort":"partial new", "model_hash":new_hash, "events":0})
                self.matches.write_text("partial new normalized history")
                bot.atomic_json(manifest, {"derived":{"cohort":"partial new"}})
                bot.atomic_json(new_registry, {"model_hash":new_hash, "events":0})
                connection.execute("INSERT INTO audit(event) VALUES ('failed refresh retained')")
                connection.commit()
                raise RuntimeError("forced v2 stage failure")

        for path, expected_bytes in original.items():
            self.assertEqual(path.read_bytes(), expected_bytes, str(path))
        self.assertEqual(existing_registry.read_bytes(), existing_registry_bytes)
        self.assertEqual(bot.read_json(new_registry), {"model_hash":new_hash, "events":0})
        self.assertEqual(connection.execute("SELECT event FROM audit ORDER BY id").fetchall(),
                         [("before refresh",), ("failed refresh retained",)])


if __name__=="__main__":
    unittest.main()
