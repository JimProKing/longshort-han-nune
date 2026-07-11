# 롱숏 한눈에

BTC, ETH, XRP 무기한 선물 기준으로  
롱·숏 비율, 지지·저항, 진입/손절/익절 시나리오를 한 화면에서 보는 웹앱입니다.

**데모:** https://web-production-e7d0f.up.railway.app/

Binance / Bybit, Hyperliquid, Kraken 공개 API를 사용합니다.  
API 키는 필요 없습니다.

---

## 왜 만들었는지

롱숏 비율 보는 사이트, 차트, 하이퍼리퀴드, 메모장이 늘 따로 있었습니다.  
매일 탭을 여러 개 띄우는 게 번거로워서, 제가 실제로 볼 내용만 모았습니다.

투자 자문이 아닙니다.  
공개 데이터와 간단한 기술적 휴리스틱으로 만든 **개인 참고용** 도구입니다.  
레버리지·청산·슬리피지는 본인이 판단해야 합니다.

---

## 기능

**Binance**
- 전체 계정 롱/숏 비율
- OI 기준 추정 롱·숏 규모(달러)
- 탑트레이더 계정·포지션 비율, 테이커 매수/매도 대금
- 지지·저항(스윙, 피봇, 피보나치, EMA)
- 롱/숏 시나리오별 진입가, SL, TP1/TP2, R:R, 신뢰도

**Hyperliquid / Kraken**
- 미결제약정(OI), 펀딩비, 24시간 거래대금, 마크가  
- 계정 단위 롱/숏 비율은 해당 거래소 공개 API에 없어서 제공하지 않습니다.

---

## 로컬 실행

```bash
cd crypto-ls-analyzer
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저: http://localhost:8000

---

## 배포

현재 배포 주소: https://web-production-e7d0f.up.railway.app/

직접 올리려면:

1. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub**
2. `JimProKing/longshort-han-nune` 선택
3. **Root Directory는 비워 두기** (레포 루트가 곧 앱 루트)
4. 배포 후 도메인 연결

`PORT`는 Railway가 넣습니다. 별도 환경 변수는 없어도 됩니다.

### 배포가 실패할 때

| 증상 | 확인 |
|------|------|
| Dockerfile not found | Root Directory를 잘못 잡았을 때. 비우기 |
| Build failed (pip) | `requirements.txt` 재배포 (이미 고정 버전으로 맞춰 둠) |
| Healthcheck failed | Deploy 로그에 uvicorn 기동 여부 확인. `/api/health` 응답 필요 |
| 서비스는 떴는데 502 | Generate Domain 했는지, Public Networking 켜졌는지 |

Settings → Deploy 로그 맨 아래 에러 한 줄이 원인인 경우가 많습니다.

---

## API

| 경로 | 설명 |
|------|------|
| `GET /api/health` | 헬스체크 |
| `GET /api/analyze` | BTC / ETH / XRP 전체 |
| `GET /api/analyze?refresh=true` | 캐시 무시 갱신 |
| `GET /api/analyze/{BTC\|ETH\|XRP}` | 단일 자산 |

서버 캐시 TTL은 약 45초입니다.

---

## 구조

```
app/
  main.py
  services/
    binance.py      # Binance
    exchanges.py    # Hyperliquid, Kraken, 데이터 묶음
    analysis.py     # 비율·레벨 분석
    strategy.py     # 진입 / SL / TP
static/             # 프론트엔드 (HTML / CSS / JS)
```

백엔드: FastAPI, httpx, uvicorn  
프론트: 별도 프레임워크 없음

---

## 만든 사람

이영찬 (Young Chan Lee)

- Kakao: caramel112  
- Email: caramel2516@naver.com  
- LinkedIn: [young-chan-lee-9304a3287](https://www.linkedin.com/in/young-chan-lee-9304a3287/)  
  (비로그인 시 LinkedIn이 로그인 화면을 띄울 수 있습니다)

---

## 면책

본 프로젝트는 금융 투자 권유나 자문이 아닙니다.  
이용으로 인한 손실에 대해 제작자는 책임지지 않습니다.
