"""Usage: python import_policies.py [--dir path] [--replace]"""
import argparse
from pathlib import Path
from db import init_db
from policy_data import import_policy_file

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dir', default=str(Path(__file__).resolve().parent/'data'/'policies'))
    parser.add_argument('--replace',action='store_true',help='Intentional same-version content overwrite; avoid for approved published policies')
    args=parser.parse_args()
    init_db(); count=0
    for file in sorted(Path(args.dir).glob('*.json')):
        if file.name.startswith('_'):continue
        state,version=import_policy_file(file,replace=args.replace)
        print(f'{file.name}: {state} ({version})')
        count+=1
    if not count: print('No policy JSON files found')

if __name__=='__main__':main()
