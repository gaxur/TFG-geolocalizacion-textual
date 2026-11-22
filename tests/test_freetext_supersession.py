import hashlib,json,os,sqlite3,subprocess,sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
SID='freetext-application-00000000-0000-0000-0000-000000000001'
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def test_supersession_archives_marks_unknown_and_is_idempotent(tmp_path):
    state=tmp_path/'state';session=state/'sessions'/SID;session.mkdir(parents=True);(session/'.transition.lock').write_bytes(b'');document={'session_id':SID,'status':'waiting_user','stop_reason':None,'profile_binding':{'profile_id':'p','executor_identity_sha256':'a'*64},'description_es':'Descripción','description_sha256':'b'*64,'state':{'stages':[{'ranking':{'results':[{'rank':1}]}}]},'events':[],'expires_at':'2099-01-01T00:00:00Z'};document['session_sha256']=hashlib.sha256(canonical(document)).hexdigest();(session/'session.json').write_bytes(canonical(document)+b'\n');(session/'ranking-0.json').write_text('{}')
    ledger=state/'freetext-application.sqlite3';connection=sqlite3.connect(ledger);connection.execute('CREATE TABLE sessions(session_id TEXT PRIMARY KEY,profile_id TEXT,status TEXT)');connection.execute('INSERT INTO sessions VALUES (?,?,?)',(SID,'p','waiting_user'));connection.commit();connection.close();archive=tmp_path/'archive';command=[sys.executable,str(ROOT/'scripts/supersede_freetext_application_session.py'),'--state-root',str(state),'--session-id',SID,'--expected-session-sha256',document['session_sha256'],'--archive-root',str(archive),'--superseding-runtime','resident-sequential-v1']
    first=json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout);stored=json.loads((session/'session.json').read_text());assert stored['status']=='unknown' and stored['stop_reason']=='runtime_identity_superseded_no_retry';assert json.loads((archive/SID/'session.json').read_text())['status']=='waiting_user';assert first['manifest_sha256']==json.loads((archive/SID/'archive-manifest.json').read_text())['manifest_sha256']
    second=json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout);assert second['idempotent'] is True and second['manifest_sha256']==first['manifest_sha256']


def test_profile_generator_rejects_open_ledger_before_identity(tmp_path):
    state=tmp_path/'state';state.mkdir();connection=sqlite3.connect(state/'freetext-application.sqlite3');connection.execute('CREATE TABLE sessions(status TEXT)');connection.execute("INSERT INTO sessions VALUES ('waiting_user')");connection.commit();connection.close();environment={**os.environ,'ATLAS_FREETEXT_APPLICATION_STATE_ROOT':str(state)};result=subprocess.run([sys.executable,str(ROOT/'scripts/generate_freetext_application_profile.py'),'--output',str(tmp_path/'profile.json')],capture_output=True,text=True,env=environment);assert result.returncode!=0 and 'sesiones abiertas' in result.stderr;assert not (tmp_path/'profile.json').exists()
