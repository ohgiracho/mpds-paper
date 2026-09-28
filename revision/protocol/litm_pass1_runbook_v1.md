# LITM direct-Anthropic Pass 1 runbook v1

Status: packets and evaluator inputs frozen; no Claude API call made during preparation  
Config: `config/independent_judge_sonnet5_pass1_litm_v1.json`  
Packets: 12 case–replicate packets, three anonymous candidates per packet

## Frozen implementation

- Verbatim public GitHub IHQ rubric
- Existing supplementary Pass 1 validity module
- Existing direct-Anthropic `claude-sonnet-5` forced-tool transport
- Existing score fields, flags, rationales, caps, and strict local validation
- Candidate cardinality adapted only from A–D to A–C

The blind key must never be placed in the Claude request or shared with the evaluator.

## Pilot

Run the first packet only:

```powershell
python tools\run_pass1_litm_anthropic.py --mode main --packet evaluation\blind_packets_litm_position_control_v1\case_29__rep_01.md --output-dir results\pass1_sonnet5_litm_position_control_v1 --model claude-sonnet-5 --max-output-tokens 6000 --max-attempts 2 --api-key-env ANTHROPIC_API_KEY --endpoint https://api.anthropic.com/v1/messages
```

Require HTTP success, returned model metadata, exactly Candidate A–C, eight integer scores per candidate, four valid flags, nonempty rationales, three derived rows, and `COMPLETE` before proceeding.

## Remaining batch

After the pilot passes, submit the other 11 frozen packets in filename order using the identical command settings. Do not rescore a packet whose run manifest is already `COMPLETE`. Preserve failed attempts and retry only according to the frozen rule: HTTP/API failures stop; one deterministic retry is permitted only for a structurally invalid HTTP-200 response.

## Completion checks

- 12/12 packet manifests `COMPLETE`
- 36/36 candidate score rows
- strict validator `PASS`
- blind key joined only after all scoring completes
- analysis aggregated to case means after three replicates; inferential `n = 4`

The separate deterministic evidence-utilization parser correction is not part of Claude Pass 1 and must remain versioned separately.
