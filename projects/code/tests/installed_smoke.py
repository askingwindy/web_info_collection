"""仅用标准库驱动已安装 CLI，确保测试不依赖源码导入。"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess


def run(python, output):
    output=Path(output).resolve()
    output.mkdir(parents=True)
    batch=output/'batch'
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    def invoke(args, expected=0):
        result=subprocess.run([str(python),'-m','webcollect',*map(str,args)],cwd=output,env=env,capture_output=True,text=True)
        if result.returncode!=expected:
            raise AssertionError(f'{args}: expected {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}')
        return json.loads(result.stdout) if result.stdout.strip() else {}
    manifest=invoke(['scaffold','--output',batch])
    sample=batch/'samples'/manifest['sample_id']
    report=output/'report.json'
    result=invoke(['validate',sample,'--mode','integration','--manifest',batch/'manifest.json','--report',report])
    assert result['structural_pass'] is True and result['delivery_ready'] is False
    assert result['total_steps']==6 and result['effective_steps']==5
    invoke(['metadata',batch,'--output',output/'export.csv'])
    with (output/'export.csv').open(newline='') as f:
        row=next(csv.DictReader(f))
    for key in ['task_type','screen_resolution','actions']:assert isinstance(json.loads(row[key]),list)
    assert int(row['bytes'])==sum(p.stat().st_size for p in sample.rglob('*') if p.is_file())
    invoke(['validate',sample,'--manifest',batch/'manifest.json'],1)
    invoke(['validate',sample],2)
    invoke(['scaffold','--output',batch],2)
    invoke(['metadata',batch,'--output',output/'export.csv'],2)
    assert invoke(['validate',sample,'--mode','integration'])['structural_pass']
    summary={'installed_smoke_pass':True,'executed_outside_source':True,
             'schema_resources_available':True,'csv_roundtrip_pass':True,
             'exit_codes_verified':[0,1,2],'overwrite_rejected':True,
             'delivery_ready':False,'python':str(python),'sample_id':manifest['sample_id']}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--python',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    run(args.python.absolute(),args.output)
