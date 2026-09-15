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
    def test_requested_direct_reads_require_bytes_and_zero_fallbacks(self):
        sys.path.insert(0,str(TOOLS))
        try:
            run=load('full_run_direct','inkling_ep_full_run.py')
        finally:
            sys.path.pop(0)
        status=dict(returncode=0,stop_reason=None,protected_processes_unchanged=True)
        driver=dict(returncode=0,status=status,report={k:True for k in
            ['full_model','reference_comparison','greedy_match','numerical_match','correctness_verified']})
        status=dict(status,job=dict(env=dict(CASCADIA_INKLING_UNCACHED_READS='1')))
        def check(size,fallbacks):
            b=dict(cpu_calls=1,fused=None,uncached_read_bytes=size,uncached_read_fallbacks=fallbacks)
            w=dict(returncode=0,status=status,log='backend_final='+json.dumps(b))
            return run.qualification(driver,{'charlie':w},{'charlie':{}},False)['completed']
        self.assertTrue(check(4096,0))
        self.assertFalse(check(0,0))
        self.assertFalse(check(4096,1))

    def test_recording_is_not_accepted_as_a_correctness_comparison(self):
        sys.path.insert(0,str(TOOLS))
        try: run=load('full_run_recording','inkling_ep_full_run.py')
        finally: sys.path.pop(0)
        status=dict(returncode=0,stop_reason=None,protected_processes_unchanged=True)
        report=dict(full_model=True,reference_comparison=False,teacher_forced=False,
                    tensor_errors=[],generated_ids=[[1,2]],tokens_per_case=2,correctness_verified=False)
        driver=dict(returncode=0,status=status,report=report)
        worker=dict(returncode=0,status=status,log='backend_final='+json.dumps(dict(cpu_calls=1,fused=None)))
        self.assertFalse(run.qualification(driver,{'alpha':worker},{'alpha':{}},False)['completed'])
        self.assertTrue(run.qualification(driver,{'alpha':worker},{'alpha':{}},False,recording=True)['completed'])
        report['generated_ids']=[[1]]
        self.assertFalse(run.qualification(driver,{'alpha':worker},{'alpha':{}},False,recording=True)['completed'])

    def test_twelve_views_preserve_every_physical_owner_and_aggregate_capacity(self):
        sys.path.insert(0,str(TOOLS))
        try: topology=load('full_topology','inkling_ep_topology.py')
        finally: sys.path.pop(0)
        parent=json.loads((TOOLS.parent/'docs/perf/inkling-ep-full/placement.json').read_text())
        plan=topology.split_plan(parent,4)
        self.assertEqual(len(plan['workers']),12)
        for before,after in zip(parent['layers'],plan['layers']):
            for owners,views in zip(before,after):
                self.assertEqual(owners,[wi//4 for wi in views])
                self.assertEqual(len(set(views)),len(views))
        for pi,worker in enumerate(parent['workers']):
            self.assertLessEqual(sum(w['expert_capacity_bytes'] for w in plan['workers'][pi*4:pi*4+4]),
                                 worker['expert_capacity_bytes'])
        self.assertTrue(all(w['expert_capacity_bytes']>0 for w in plan['workers']))

    def test_view_preparation_script_parses_before_remote_mutations(self):
        sys.path.insert(0,str(TOOLS))
        try:topology=load('full_topology_script','inkling_ep_topology.py')
        finally:sys.path.pop(0)
        scripts=[]
        def capture(host,script,timeout):
            ast.parse(script,feature_version=(3,11));scripts.append(script);return '{}'
        path=TOOLS.parent/'docs/perf/inkling-ep-full/placement.json'
        with patch.object(topology,'remote',capture):
            topology.prepare_views(path,4,{h:{} for h in ['alpha','beta','charlie']})
        self.assertEqual(len(scripts),3)
        self.assertTrue(all('logical placement bytes differ' in script for script in scripts))

    def test_firewall_uses_native_windows_program_path(self):
        sys.path.insert(0,str(TOOLS))
        try:
            run=load('full_run_firewall','inkling_ep_full_run.py')
        finally:
            sys.path.pop(0)
        calls=[]
        def capture(host,script,timeout):
            # Extract the structured subprocess argument without executing it.
            tree=ast.parse(script)
            argv=ast.literal_eval(tree.body[1].value.args[0])
            calls.append(argv[-1])
            return 'ok'
        with patch.object(run,'remote',capture): run.firewall('alpha',True)
        self.assertIn("-Program 'C:\\Users\\tatef\\inkling-ep-lan-20260915\\bin-full\\inkling_ep_worker.exe'",calls[0])
        self.assertIn('-RemoteAddress 192.168.0.188',calls[0])

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
            streaming=True,calls=12,device='GPU',fusion_profiles={'2':'MOECompressed'},up_scale_exponent={'2':4}))
        def check(b=backend, d=driver, s=status):
            worker=dict(returncode=0,status=s,log='backend_final='+json.dumps(b))
            return run.qualification(d,{'alpha':worker},{'alpha':dict(owned_layers=[2],
                fused_shards={'2':dict(up_scale_exponent=4)})},True)['completed']
        self.assertTrue(check())
        import copy
        for key,value in [('cpu_calls',1),('ov_fallbacks',1)]:
            bad=copy.deepcopy(backend);bad[key]=value;self.assertFalse(check(b=bad))
        for key,value in [('errors',1),('device','CPU'),('fusion_profiles',{}),('streaming',False),('up_scale_exponent',{'2':0})]:
            bad=copy.deepcopy(backend);bad['fused'][key]=value;self.assertFalse(check(b=bad))
        bad=copy.deepcopy(driver);bad['report']['greedy_match']=False
        self.assertFalse(check(d=bad))
        self.assertFalse(check(s=dict(status,protected_processes_unchanged=False)))
        self.assertFalse(run.qualification(driver,{}, {'alpha':dict(owned_layers=[2])},True)['completed'])

    def test_short_runs_require_collective_gpu_coverage_not_unused_views(self):
        sys.path.insert(0,str(TOOLS))
        try:run=load('full_run_coverage','inkling_ep_full_run.py')
        finally:sys.path.pop(0)
        status=dict(returncode=0,stop_reason=None,protected_processes_unchanged=True)
        driver=dict(returncode=0,status=status,report={k:True for k in
            ['full_model','reference_comparison','greedy_match','numerical_match','correctness_verified']})
        def worker(layer):
            stats=dict(errors=0,fused_required=True,streaming=True,calls=1,device='GPU',fusion_profiles={str(layer):'MOECompressed'})
            return dict(returncode=0,status=status,log='backend_final='+json.dumps(dict(cpu_calls=0,ov_fallbacks=0,fused=stats)))
        inventories={h:dict(owned_layers=[2,3]) for h in ['alpha','beta']}
        self.assertTrue(run.qualification(driver,{'alpha':worker(2),'beta':worker(3)},inventories,True)['completed'])
        self.assertFalse(run.qualification(driver,{'alpha':worker(2),'beta':worker(2)},inventories,True)['completed'])
        self.assertFalse(run.qualification(driver,{'alpha':worker(2),'beta':worker(4)},inventories,True)['completed'])

    def test_requested_lossless_wire_requires_observed_half_size_payloads(self):
        sys.path.insert(0,str(TOOLS))
        try:run=load('full_run_half_wire','inkling_ep_full_run.py')
        finally:sys.path.pop(0)
        status=dict(returncode=0,stop_reason=None,protected_processes_unchanged=True)
        driver=dict(returncode=0,status=status,report={k:True for k in
            ['full_model','reference_comparison','greedy_match','numerical_match','correctness_verified']})
        backend=dict(cpu_calls=0,ov_fallbacks=0,wire_f16_replies=1,wire_f32_replies=0,
                     wire_tensor_bytes=24,wire_f32_equivalent_bytes=48,
                     fused=dict(errors=0,fused_required=True,streaming=True,calls=1,device='GPU',fusion_profiles={'2':'MOECompressed'}))
        def check(b):
            worker=dict(returncode=0,status=status,log='backend_final='+json.dumps(b))
            return run.qualification(driver,{'alpha':worker},{'alpha':dict(owned_layers=[2],lossless_wire_required=True)},True)['completed']
        self.assertTrue(check(backend))
        for key,value in [('wire_f16_replies',0),('wire_f32_replies',1),('wire_tensor_bytes',48),('wire_f32_equivalent_bytes',0)]:
            self.assertFalse(check(dict(backend,**{key:value})))

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
