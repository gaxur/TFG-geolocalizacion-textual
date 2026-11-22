import asyncio

from backend.atlas_api.model_gate import ModelGate


def test_try_acquire_is_atomic_without_queueing():
    async def scenario():
        gate=ModelGate();ready=asyncio.Event();release=asyncio.Event();outcomes=[]
        async def contender(name):
            await ready.wait();accepted=gate.try_acquire();outcomes.append((name,accepted));
            if accepted:
                await release.wait();gate.release()
        tasks=[asyncio.create_task(contender('a')),asyncio.create_task(contender('b'))];ready.set();await asyncio.sleep(0);release.set();await asyncio.gather(*tasks);return outcomes
    outcomes=asyncio.run(scenario());assert sum(accepted for _,accepted in outcomes)==1
