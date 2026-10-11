"""Scan publishable evidence + staged additions, never print matched secrets."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from history_v2_probe.publication_safety import findings

def scan(paths):
    issues=[];count=0;pdfs=0;exceptions=[]
    exception_file=ROOT/'contracts/synthetic-scan-exceptions.json'
    approved=json.loads(exception_file.read_text())['files'] if exception_file.exists() else {}
    for path in sorted(set(paths)):
        if not path.is_file() or '__pycache__' in path.parts or '.venv' in path.parts:continue
        raw=path.read_bytes();count+=1;rules=set(findings(raw))
        if path.suffix.lower()=='.pdf':
            from pypdf import PdfReader
            try:
                reader=PdfReader(path);text='\n'.join(page.extract_text() or '' for page in reader.pages)
                rules.update(findings(text));pdfs+=1
            except Exception:rules.add('pdf_scan_incomplete')
        if path.suffix.lower()=='.html':
            sys.path.insert(0,str(ROOT/'scripts'))
            from minimize_sisal_page import retain_anchors
            try:
                if retain_anchors(raw)!=raw:rules.add('unminimized_html')
            except Exception:rules.add('unminimized_html')
        name=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
        exception=approved.get(name)
        test_source=name.endswith('.py') and (name.startswith('tests/') or name.startswith('regression/adapter/tests/') or name.startswith('regression/provider/tests/'))
        if rules and test_source and path.is_relative_to(ROOT) and exception and exception['sha256']==hashlib.sha256(raw).hexdigest() and rules==set(exception['rules']):
            exceptions.append({'file':name,'rules':sorted(rules),'sha256':exception['sha256'],'reason':exception['reason']})
        elif rules:issues.append({'file':name,'rules':sorted(rules)})
    return {'files_scanned':count,'pdf_texts_scanned':pdfs,'findings':issues,'reviewed_synthetic_test_code_exceptions':exceptions,'passed':not issues,'matched_values_retained':False,'limitation':'Known credential formats and contextual patterns; not proof against unknown secrets. Exceptions apply only to exact reviewed synthetic test source bytes, never evidence.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    paths=[]
    # Scan code/documentation as well, both locally and in a clean CI checkout.
    paths.extend(p for p in ROOT.rglob('*') if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts)
    # All publishable evidence, including inherited regression fixtures and PDFs.
    for name in ('cases','live','regression','examples'):
        paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix not in ('.py','.pyc'))
    repo=ROOT.parents[1]
    paths.extend((repo/'.github/workflows').glob('history-v2*.yml'))
    added=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACM','-z'],cwd=repo).decode().split('\0')
    paths.extend(repo/name for name in added if name and (repo/name).is_file())
    # Reports are part of the delivery too; retain safe rule names only.
    paths.extend((ROOT/'reports').glob('*.json'));paths.extend((ROOT/'reports').glob('*.log'))
    result=scan(paths)
    if args.output:(ROOT/args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()
