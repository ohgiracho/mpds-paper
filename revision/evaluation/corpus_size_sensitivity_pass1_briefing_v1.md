# Corpus-size sensitivity generation 및 blind Pass 1 브리핑

## 실행 및 무결성 상태

- Generation: 4 cases × 4 corpus sizes × 3 replicates = 48/48 COMPLETE.
- Generation model: Vertex AI `gemini-2.5-pro`, temperature 0.5, 3 rounds.
- Blind evaluation: 12 packets × 4 candidates = 48/48 candidate scores.
- Evaluator: official Anthropic Messages API의 `claude-sonnet-5`.
- 이전 공식 4-condition Anthropic Pass 1의 runner, prompt, schema, original IHQ rubric, supplementary module, validator를 변경 없이 재사용했다.
- Provider tool schema SHA-256은 이전 공식 실행과 동일했다.
- 후보 위치 균형: corpus size 100/250/500/1000이 Candidate A/B/C/D 각각에 정확히 3회씩 배치됐다.
- 유료 호출 전 동결한 fixed files, generation source, packets 총 124개를 호출 후 다시 검사했고 hash mismatch는 0건이었다.
- Anthropic 결과는 12/12가 첫 시도에 HTTP 200 및 local validation을 통과했다. 구조 재시도와 누락 점수는 0건이다.

## Blind Pass 1 점수

각 corpus size는 4 cases × 3 replicates = n=12이다. 값은 mean ± sample SD이다.

| Corpus size per pool | IHQ without CPI (0–15) | Full IHQ (0–20) | Scientific-practical validity (0–20) |
|---:|---:|---:|---:|
| 100 | 8.25 ± 1.14 | 11.17 ± 1.11 | 13.08 ± 1.68 |
| 250 | 8.17 ± 1.59 | 10.83 ± 2.04 | 12.75 ± 1.54 |
| 500 | 8.00 ± 1.71 | 10.67 ± 2.53 | 13.08 ± 1.68 |
| 1000 | 8.58 ± 1.78 | 11.33 ± 2.23 | 13.33 ± 2.02 |

500 대비 paired mean difference는 다음과 같다.

| Comparison | Δ IHQ without CPI | Δ Full IHQ | Δ validity |
|---|---:|---:|---:|
| 100 − 500 | +0.25 | +0.50 | 0.00 |
| 250 − 500 | +0.17 | +0.17 | −0.33 |
| 1000 − 500 | +0.58 | +0.67 | +0.25 |

과학적으로 중대한 오류와 temporal-cutoff 위반 flag는 모든 size에서 0건이었다. `fixed_task_constraint_violation=uncertain`은 size 100에서 1건, size 1000에서 2건이었고, `infeasible_primary_process=uncertain`은 size 250에서 1건이었다. 확정적인 yes flag는 없었다.

## Generation 사용량

아래 prompt/output token과 runtime은 최종 COMPLETE 12개씩만 합한 값이다. `All-attempt prompt tokens`는 보존된 실패 실행까지 포함한 실제 소모량이다.

| Corpus size | COMPLETE | Successful-output prompt tokens | Successful-output tokens | API calls in COMPLETE runs | COMPLETE runtime | All-attempt prompt tokens | Preserved failed run attempts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 12 | 3,772,344 | 174,970 | 124 | 1.50 h | 4,172,017 | 2 |
| 250 | 12 | 8,212,741 | 177,970 | 145 | 2.25 h | 11,724,934 | 7 |
| 500 | 12 | 16,518,618 | 193,632 | 144 | 2.34 h | 18,709,996 | 3 |
| 1000 | 12 | 35,363,332 | 206,475 | 146 | 2.50 h | 37,660,131 | 1 |

- 전체 실제 generation 시도: 700 API calls = 635 success + 65 failed/transient calls.
- 보존된 batch-level failed run attempts: 13건. 원인은 final evidence-pointer validation 7건, 429/resource exhaustion 4건, empty response 1건, stderr 없이 중단된 wrapper attempt 1건이었다. 최종 미해결 실패는 0건이다.
- 재시도를 포함한 전체 generation 사용량: prompt 72,267,078 tokens, candidate output 920,166 tokens, thought 1,688,896 tokens, total 74,876,140 tokens.
- 최종 COMPLETE 실행만의 누적 runtime은 8.60 h이며, 실패 보존 시도까지 더한 누적 runtime은 10.58 h이다.
- Anthropic blind Pass 1: 12 calls, input 176,578 tokens, output 33,655 tokens, elapsed 392.23 s.

## 1000-paper context 해석

1000-paper 조건에서 context-window 초과는 발생하지 않았다. 유일한 보존 실패 run은 양쪽 debater의 evidence pointer를 모두 포함해야 한다는 final synthesis validation 실패였으며 context-limit 오류가 아니었다.

다만 70,000-character 규칙은 **전체 request cap이 아니다**. 각 pool/persona에 대해 70,000자를 선택하지만, debate-turn prompt에는 full corpus text도 포함된다. 따라서 모든 size에서 persona selection은 이미 truncation됐지만 실제 prompt token은 corpus size에 따라 계속 증가했다. COMPLETE 실행 기준으로 1000-paper prompt token은 500-paper의 약 2.14배였다.

## 타당한 결론

이 결과는 500 abstracts가 점수상 유일하거나 최적인 값이라는 주장을 지지하지 않는다. 오히려 100–1000 범위에서 평균 품질 차이가 작고 단조 증가가 없어서, MPDS 결과가 특정 corpus size에 강하게 의존하지 않는다는 robustness 결과로 해석하는 것이 타당하다.

500은 다음처럼 방어하는 것이 안전하다.

1. 성능을 사후 최적화한 값이 아니라, 좁은 retrieval pool에서 관련 문헌을 누락할 위험을 줄이기 위해 사전 선택한 coverage-oriented operating point이다.
2. 1000으로 확대했을 때 500 대비 평균 증가는 IHQ without CPI +0.58, Full IHQ +0.67, validity +0.25에 그쳤다.
3. 반면 1000은 500보다 COMPLETE-run prompt token이 약 2.14배 필요했다.
4. 따라서 500은 “formal optimum”이 아니라 broader coverage와 compute cost 사이의 practical compromise이다.

## Reviewer response 초안

> To examine whether the choice of 500 abstracts materially affected the MPDS output, we performed a corpus-size sensitivity analysis using nested top-N retrieval sets (100, 250, 500, and 1000 abstracts per literature pool) for four representative cases with three independent replicates per setting. All other generation parameters were fixed, and the 48 outputs were evaluated using the same frozen blind Pass 1 protocol as our previous official Anthropic evaluation. Mean Full IHQ scores were 11.17, 10.83, 10.67, and 11.33 for corpus sizes 100, 250, 500, and 1000, respectively; the corresponding scientific-practical validity scores were 13.08, 12.75, 13.08, and 13.33. Thus, quality did not change monotonically with corpus size, and increasing the corpus from 500 to 1000 produced only small average gains while increasing generation prompt tokens by approximately 2.14-fold. We therefore clarify that 500 abstracts was selected as a pre-specified, coverage-oriented practical operating point rather than a formally optimized value. The sensitivity analysis indicates that the main output-quality conclusions are not strongly dependent on this specific corpus size within the tested range.

## Protocol note

The corpus-size sensitivity outputs were evaluated using the same frozen blind Pass 1 protocol used in the previous official Anthropic evaluation; only the candidate conditions differed.

원본 `final.txt`와 judge packet body의 직접 hash는 일치하지 않는다. 이는 이전 공식 packet builder와 동일한 frozen `clean_final` 변환이 evidence map/appendix/reference sections를 제거하기 때문이다. 정제된 source body와 packet body의 hash는 48/48 일치했다.
