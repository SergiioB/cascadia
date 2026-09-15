"""Correctness gates and service preservation for full-model qualification."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, TOOLS/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardTests(unittest.TestCase):
    def execute(self, pause, ci=False):
        now, events = [0.0], []

        class Process:
            def __init__(self, pid):
                self.pid = pid
                self.info = dict(name='ovms.exe', create_time=1234.)
            def cpu_percent(self):
                return 40. if 1 <= now[0] < 2 else 0.
            def is_running(self): return True
            def cpu_affinity(self, value): pass
            def create_time(self): return 5678.
            def memory_info(self): return types.SimpleNamespace(rss=2**20)
            def suspend(self): events.append(('suspend', self.pid))
            def resume(self): events.append(('resume', self.pid))

        service = Process(11)
        def processes(fields):
            result = [service]
            if ci and now[0] >= 2:
                runner = Process(12)
                runner.info = dict(name='Runner.Worker.exe', create_time=2345.)
                result.append(runner)
            return result
        psutil = types.SimpleNamespace(Process=Process, process_iter=processes,
            cpu_count=lambda:16, virtual_memory=lambda:types.SimpleNamespace(available=24*2**30),
            NoSuchProcess=RuntimeError)
        with patch.dict(sys.modules, {'psutil':psutil}):
            guard = load('test_guard', 'inkling_ep_guard.py')

        class Child:
            pid = 42
            returncode = None
            def __init__(self, *args, **kwargs): pass
            def poll(self):
                if now[0] >= 5 and self.returncode is None: self.returncode = 0
                return self.returncode
            def terminate(self):
                events.append(('terminate',self.pid)); self.returncode=1
            def kill(self): raise AssertionError('unexpected hard kill')
            def wait(self, timeout): return self.returncode

        with tempfile.TemporaryDirectory() as td:
            root=Path(td); exe=root/'worker.exe';exe.write_bytes(b'test')
            job=dict(label='qualification',argv=[str(exe)],cores=[0,1],seconds=10,
                     pause_for_service=pause,min_available_gib=12,max_rss_gib=4)
            clock=types.SimpleNamespace(monotonic=lambda:now[0],sleep=lambda t:now.__setitem__(0,now[0]+t))
            with patch.object(guard,'time',clock), patch.object(guard.subprocess,'Popen',Child), \
                 patch.object(guard.subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0,create=True), \
                 patch('builtins.print'):
                try: guard.run(root,job)
                except SystemExit: pass
            return events,json.loads((root/'qualification.status.json').read_text())

    def test_service_activity_pauses_only_our_process_and_resumes_after_quiet(self):
        events,result=self.execute(True)
        self.assertEqual(events,[('suspend',42),('resume',42)])
        self.assertEqual(result['returncode'],0)
        self.assertTrue(result['protected_processes_unchanged'])
        self.assertEqual(result['service_pause_count'],1)
        self.assertGreaterEqual(result['service_pause_seconds'],2)

    def test_default_guard_still_stops_own_job_when_service_is_busy(self):
        events,result=self.execute(False)
        self.assertEqual(events,[('terminate',42)])
        self.assertEqual(result['stop_reason'],'existing inference service became busy')

    def test_ci_still_terminates_even_a_suspended_test(self):
        events,result=self.execute(True,ci=True)
        self.assertEqual(events,[('suspend',42),('terminate',42)])
        self.assertEqual(result['stop_reason'],'CI job started')


class OperatorTests(unittest.TestCase):
    def test_qualification_requires_output_gpu_coverage_and_service_evidence(self):
        sys.path.insert(0,str(TOOLS))
        try:
            run=load('full_run_gate','inkling_ep_full_run.py')
        finally:
            sys.path.pop(0)
        status=dict(returncode=0,stop_reason=None,protected_processes_unchanged=True)
        driver=dict(returncode=0,status=status.copy(),report={k:True for k in
            ['full_model','reference_comparison','greedy_match','numerical_match','correctness_verified']})
        backend=dict(cpu_calls=0,ov_fallbacks=0,fused=dict(errors=0,fused_required=True,
            streaming=True,calls=12,device='GPU',fusion_profiles={'2':'MOECompressed'}))
        def check(b=backend, d=driver, s=status):
            worker=dict(returncode=0,status=s,log='backend_final='+json.dumps(b))
            return run.qualification(d,{'alpha':worker},{'alpha':dict(owned_layers=[2])},True)['completed']
        self.assertTrue(check())
        import copy
        for key,value in [('cpu_calls',1),('ov_fallbacks',1)]:
            bad=copy.deepcopy(backend);bad[key]=value;self.assertFalse(check(b=bad))
        for key,value in [('errors',1),('device','CPU'),('fusion_profiles',{}),('streaming',False)]:
            bad=copy.deepcopy(backend);bad['fused'][key]=value;self.assertFalse(check(b=bad))
        bad=copy.deepcopy(driver);bad['report']['greedy_match']=False
        self.assertFalse(check(d=bad))
        self.assertFalse(check(s=dict(status,protected_processes_unchanged=False)))
        self.assertFalse(run.qualification(driver,{}, {'alpha':dict(owned_layers=[2])},True)['completed'])

    def test_generated_preflight_script_supports_nuc_python311(self):
        sys.path.insert(0,str(TOOLS))
        try:
            run=load('full_run','inkling_ep_full_run.py')
            def parse(host,script,timeout):
                ast.parse(script,feature_version=(3,11))
                return '{}'
            with patch.object(run,'remote',parse):
                run.preflight('charlie',2,'abc',True,'reference')
        finally:
            sys.path.pop(0)

    def test_staging_paths_reject_directory_escape(self):
        stage=load('full_stage','inkling_ep_full_stage.py')
        for value in ['../model.bin','/model.bin','C:/model.bin','experts/../../x','experts\\x','experts//x','']:
            with self.assertRaises(ValueError): stage.safe_name(value)
        self.assertEqual(stage.safe_name('experts/layer_02/expert_001.bin'),'experts/layer_02/expert_001.bin')


if __name__=='__main__': unittest.main()
