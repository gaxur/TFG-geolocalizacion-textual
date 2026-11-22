FROM crosstext2loc-gb10:f511
WORKDIR /workspace/project
RUN mkdir -p /workspace/project/data/processed /workspace/project/data/embeddings /workspace/project/external /workspace/project/checkpoints/CrossText2Loc
COPY backend ./backend
COPY src ./src
RUN mkdir -p research
COPY research/dq_pilot_iterative_controller_v1.py research/dq_pilot_real_adapters_v1.py research/dq_pilot_translation_v1.py ./research/
COPY research/dq_pilot_supervised_v1.py research/dialogue_visual_generative_v1.py research/dq_pilot_zero_shot_v1.py ./research/
COPY research/dq_pilot_supervised_visual_v1.py ./research/
COPY research/ct2l_supervisor_v3.py research/dialogue_transition_runner_dqdev2.py ./research/
RUN mkdir -p scripts config schemas
RUN mkdir -p docker
COPY scripts/run_mvp1_api.sh scripts/run_dialogue_freetext_worker.py scripts/run_mvp_dialogue_worker.py scripts/run_mvp_ephemeral_retrieval_worker.py scripts/generate_freetext_application_profile.py ./scripts/
COPY config/madrid_f46_retriever.json config/madrid.yaml config/madrid_f4_visual_gallery_25m.json config/madrid_f4_visual_gallery_50m.json config/interactive_dialogue_multiturn.json config/interactive_dialogue_freetext_v1.json config/interactive_dialogue_freetext_application_v1.json config/dialogue_freetext_application_v1.json config/freetext_application_approval_d098.json ./config/
COPY schemas/atlas-dialogue-freetext-application-profile-v1.schema.json ./schemas/
COPY docker/ollama-status-nginx.conf ./docker/
COPY AGENTS.md README.md ./
