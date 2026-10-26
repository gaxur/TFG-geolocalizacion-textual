"""Estadística descriptiva y emparejada para evaluación visual agrupada."""
from __future__ import annotations
import math
import random
from typing import Iterable,Mapping,Sequence

def wilson_interval(successes:int,total:int,z:float=1.959963984540054)->tuple[float,float]:
 if total<=0 or not 0<=successes<=total:raise ValueError('conteos Wilson inválidos')
 p=successes/total;den=1+z*z/total;center=(p+z*z/(2*total))/den;margin=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den;return center-margin,center+margin

def exact_mcnemar(left_correct:Sequence[bool],right_correct:Sequence[bool])->dict:
 if len(left_correct)!=len(right_correct) or not left_correct:raise ValueError('pares McNemar incompatibles')
 left_only=sum(a and not b for a,b in zip(left_correct,right_correct));right_only=sum(b and not a for a,b in zip(left_correct,right_correct));n=left_only+right_only
 if n==0:p=1.0
 else:
  k=min(left_only,right_only);p=min(1.0,2*sum(math.comb(n,i) for i in range(k+1))/(2**n))
 return {'left_only':left_only,'right_only':right_only,'discordant':n,'exact_two_sided_p':p}

def grouped_accuracy(rows:Iterable[Mapping],*,group_field:str='query_id')->dict:
 groups={}
 for row in rows:groups.setdefault(row[group_field],[]).append(bool(row['correct']))
 return {'group_count':len(groups),'groups':{key:{'n':len(values),'accuracy':sum(values)/len(values)} for key,values in sorted(groups.items())},'macro_group_accuracy':sum(sum(v)/len(v) for v in groups.values())/len(groups) if groups else None}

def paired_cluster_bootstrap(rows:Sequence[Mapping],*,group_field:str='query_id',iterations:int=10000,seed:int=0)->dict:
 if not rows or iterations<100:raise ValueError('bootstrap agrupado inválido')
 groups={}
 for row in rows:groups.setdefault(row[group_field],[]).append(row)
 keys=sorted(groups);rng=random.Random(seed);deltas=[]
 for _ in range(iterations):
  sampled=[rng.choice(keys) for _ in keys];items=[row for key in sampled for row in groups[key]];deltas.append(sum(bool(r['right_correct'])-bool(r['left_correct']) for r in items)/len(items))
 deltas.sort();low=deltas[int(.025*iterations)];high=deltas[min(iterations-1,int(.975*iterations))]
 observed=sum(bool(r['right_correct'])-bool(r['left_correct']) for r in rows)/len(rows)
 return {'groups':len(keys),'rows':len(rows),'iterations':iterations,'seed':seed,'observed_accuracy_delta':observed,'percentile_95':[low,high]}
