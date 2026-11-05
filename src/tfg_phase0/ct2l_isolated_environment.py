"""Preflight CPU del intérprete aislado CT2L, sin importar Torch ni CLIP."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
from typing import Any,Mapping

from .crosstext2loc_runtime import EXPECTED_CHECKPOINT_SHA256,EXPECTED_CLIP_COMMIT,EXPECTED_CLIP_WEIGHTS_SHA256,EXPECTED_CVG_TEXT_COMMIT

class CT2LEnvironmentError(RuntimeError):pass

def digest(path:Path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

PROBE=r'''import importlib.metadata as m,importlib.util,json,sys
names=('clip','torch','torchvision','numpy','Pillow');out={'executable':sys.executable,'python':sys.version.split()[0],'prefix':sys.prefix,'base_prefix':sys.base_prefix,'distributions':{},'specs':{}}
for name in names:
 try:
  d=m.distribution(name);out['distributions'][name]={'version':d.version,'direct_url':d.read_text('direct_url.json')}
 except m.PackageNotFoundError:out['distributions'][name]=None
out['specs']['clip']=importlib.util.find_spec('clip') is not None
out['specs']['torch']=importlib.util.find_spec('torch') is not None
print(json.dumps(out,sort_keys=True))'''

def validate_ct2l_environment(manifest_path:Path,project_root:Path,*,session_config:Path|None=None)->dict[str,Any]:
    manifest=json.loads(manifest_path.read_text());required={'schema_version','contract_version','status','python_executable','python_version','environment_root','identity_lock','distributions','openai_clip','cvg_text','clip_weights','ct2l_checkpoint','gallery','cuda_initialization_allowed_in_preflight'}
    if set(manifest)!=required or manifest['contract_version']!='ct2l-isolated-python-runtime-v1' or manifest['cuda_initialization_allowed_in_preflight'] is not False:raise CT2LEnvironmentError('manifest runtime CT2L incompatible')
    python_path=project_root/manifest['python_executable'];environment=(project_root/manifest['environment_root']).resolve()
    if not python_path.is_file() or python_path.parent.parent.resolve()!=environment:raise CT2LEnvironmentError('intérprete CT2L ausente o fuera del entorno fijado')
    lock=(project_root/manifest['identity_lock']).resolve()
    if not lock.is_file():raise CT2LEnvironmentError('lock de identidad CT2L ausente')
    result=subprocess.run([str(python_path),'-I','-c',PROBE],capture_output=True,text=True,timeout=30)
    if result.returncode:raise CT2LEnvironmentError('probe del intérprete CT2L falló')
    try:probe=json.loads(result.stdout)
    except json.JSONDecodeError as error:raise CT2LEnvironmentError('probe CT2L no produjo JSON') from error
    if Path(probe['prefix']).resolve()!=environment or Path(probe['base_prefix']).resolve()==environment or probe['python']!=manifest['python_version']:raise CT2LEnvironmentError('intérprete, virtualenv o Python CT2L divergente')
    for name,version in manifest['distributions'].items():
        value=probe['distributions'].get(name)
        if not value or value['version']!=version:raise CT2LEnvironmentError(f'distribución ausente o divergente: {name}')
    if not probe['specs']['clip'] or not probe['specs']['torch']:raise CT2LEnvironmentError('módulo CT2L o Torch no localizable')
    direct=probe['distributions']['clip'].get('direct_url')
    try:direct=json.loads(direct) if direct else {}
    except json.JSONDecodeError as error:raise CT2LEnvironmentError('direct_url de clip inválido') from error
    commit=direct.get('vcs_info',{}).get('commit_id');url=direct.get('url')
    if commit!=manifest['openai_clip']['commit'] or commit!=EXPECTED_CLIP_COMMIT or url!=manifest['openai_clip']['repository']:raise CT2LEnvironmentError('procedencia o commit OpenAI CLIP divergente')
    cvg=(project_root/manifest['cvg_text']['root']).resolve();head=subprocess.run(['git','-C',str(cvg),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
    if head.returncode or head.stdout.strip()!=manifest['cvg_text']['commit'] or head.stdout.strip()!=EXPECTED_CVG_TEXT_COMMIT or digest(cvg/'utils.py')!=manifest['cvg_text']['utils_sha256']:raise CT2LEnvironmentError('identidad CVG-Text divergente')
    weights=Path(manifest['clip_weights']['path']).expanduser();checkpoint=(project_root/manifest['ct2l_checkpoint']['path']).resolve()
    if not weights.is_file() or weights.stat().st_size!=manifest['clip_weights']['size_bytes'] or digest(weights)!=manifest['clip_weights']['sha256'] or manifest['clip_weights']['sha256']!=EXPECTED_CLIP_WEIGHTS_SHA256:raise CT2LEnvironmentError('pesos CLIP divergentes')
    if not checkpoint.is_file() or checkpoint.stat().st_size!=manifest['ct2l_checkpoint']['size_bytes'] or digest(checkpoint)!=manifest['ct2l_checkpoint']['sha256'] or manifest['ct2l_checkpoint']['sha256']!=EXPECTED_CHECKPOINT_SHA256:raise CT2LEnvironmentError('checkpoint CT2L divergente')
    embedding=json.loads((project_root/manifest['gallery']['embedding_manifest']).read_text());model=embedding['model'];stored_checkpoint=embedding['checkpoint']
    if manifest['gallery']['id']!='madrid-50m' or model['openai_clip_commit']!=commit or model['openai_clip_weights_sha256']!=manifest['clip_weights']['sha256'] or model['cvg_text_commit']!=manifest['cvg_text']['commit'] or stored_checkpoint['sha256']!=manifest['ct2l_checkpoint']['sha256']:raise CT2LEnvironmentError('entorno incompatible con embeddings Madrid')
    lock_text=lock.read_text()
    for name,version in manifest['distributions'].items():
        expected=f'{name}=={version}' if name!='clip' else f'clip @ git+{manifest["openai_clip"]["repository"]}@{commit}'
        if expected not in lock_text:raise CT2LEnvironmentError(f'lock no fija {name}')
    startup=None;second_turn_startup=None
    if session_config is not None:
        entrypoint=project_root/'scripts/run_ct2l_isolated_child.py';startup_result=subprocess.run([str(python_path),'-I',str(entrypoint),'--check-child-startup','--config',str(session_config)],cwd=project_root,capture_output=True,text=True,timeout=120)
        if startup_result.returncode:raise CT2LEnvironmentError('startup real del hijo CT2L falló: '+startup_result.stderr.strip().splitlines()[-1])
        try:startup=json.loads(startup_result.stdout)
        except json.JSONDecodeError as error:raise CT2LEnvironmentError('startup hijo CT2L no produjo JSON') from error
        if startup.get('status')!='CHILD_STARTUP_CPU_PASS' or startup.get('stage_reached')!='immediately_before_CrossText2LocRetriever.load' or startup.get('torch_imported') or startup.get('clip_imported') or startup.get('cuda_initialized') or startup.get('models_loaded'):raise CT2LEnvironmentError('startup hijo CT2L no es CPU/fail-closed')
        if session_config.name=='configuration.json':
            run_root=session_config.parent
            try:state=json.loads((run_root/'state.json').read_text())
            except (OSError,json.JSONDecodeError):state={}
            if state.get('pending_answer') is not None:
                second_result=subprocess.run([str(python_path),'-I',str(entrypoint),'--check-second-turn-startup','--run-root',str(run_root)],cwd=project_root,capture_output=True,text=True,timeout=120)
                if second_result.returncode:raise CT2LEnvironmentError('startup real segundo turno CT2L falló: '+second_result.stderr.strip().splitlines()[-1])
                try:second_turn_startup=json.loads(second_result.stdout)
                except json.JSONDecodeError as error:raise CT2LEnvironmentError('startup segundo turno no produjo JSON') from error
                if second_turn_startup.get('status')!='SECOND_TURN_CHILD_STARTUP_CPU_PASS' or second_turn_startup.get('stage_reached')!='immediately_before_second_turn_retrieve_full' or second_turn_startup.get('torch_imported') or second_turn_startup.get('clip_imported') or second_turn_startup.get('cuda_initialized') or second_turn_startup.get('models_loaded') or second_turn_startup.get('run_modified') is not False:raise CT2LEnvironmentError('startup segundo turno no es CPU/fail-closed')
    return {'status':'CT2L_ISOLATED_ENV_CPU_PASS','python_executable':str(python_path.resolve()),'python_entrypoint':str(python_path),'python_version':probe['python'],'environment_root':str(environment),'base_prefix':probe['base_prefix'],'identity_lock':str(lock),'identity_lock_sha256':digest(lock),'distributions':{name:value['version'] for name,value in probe['distributions'].items()},'openai_clip_commit':commit,'openai_clip_url':url,'cvg_text_commit':head.stdout.strip(),'cvg_utils_sha256':digest(cvg/'utils.py'),'clip_weights_sha256':digest(weights),'checkpoint_sha256':digest(checkpoint),'embedding_dataset_id':embedding['embedding_dataset_id'],'child_startup':startup or 'NOT_RUN','second_turn_child_startup':second_turn_startup or 'NOT_REQUIRED','cuda_initialized':False,'models_loaded':False}
