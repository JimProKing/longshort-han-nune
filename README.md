# 롱숏 한눈에 👀📈

> 탭 17개 띄우다 멘탈 나가서 만든  
> **BTC · ETH · XRP** 무기한 선물 한 장 대시보드

바이낸스 롱숏 비율 보고,  
하이퍼리퀴드 OI 보고,  
크라켄 펀딩 보고…  
**“아 그냥 한 화면에 다 있으면 안 되나?”**

→ 그래서 만들었습니다.

---

## 이게 뭐예요?

| 보고 싶은 것 | 있어요? |
|---|---|
| 전체 계정 **롱 / 숏 %** + 추정 액수 | ✅ Binance |
| **지지 · 저항** (스윙, 피봇, 피보, EMA) | ✅ |
| **진입 / SL / TP** 시나리오 (롱·숏 둘 다) | ✅ |
| **Hyperliquid** OI · 펀딩 · 24h 대금 | ✅ |
| **Kraken** OI · 펀딩 · 24h 대금 | ✅ |
| 투자 수익 보장 | ❌ 그건 신이 함 |

> ⚠️ **투자 자문 아닙니다.**  
> 공개 데이터 + 휴리스틱으로 만든 **개인 참고용**이에요.  
> 레버리지 잘못 쓰면 잔고가 귀여운 숫자가 됩니다.

---

## 왜 만들었냐면

차트 사이트 하나,  
롱숏 사이트 하나,  
하이퍼리퀴드 하나,  
메모장에 진입가 적고…

매일 그 루틴이 귀찮아서  
**“그냥 내가 쓸 거 하나 만들자”** 했습니다.

이영찬 (Young Chan Lee) · 1인 개발  
쓸 때마다 탭 여러 개 띄우기 싫어서 직접 짬 🍜

---

## 화면에서 보이는 것들

### 1. 롱 · 숏 비율 + 액수 (Binance)
- 계정 기준 롱% / 숏%
- OI × 비율로 추정한 **달러 규모**
- 탑트레이더 포지션, 테이커 매수·매도 대금

### 2. 거래소 3대장 비교
| 거래소 | OI | 펀딩 | 24h 대금 | 계정 L/S |
|---|---|---|---|---|
| **Binance** | ✅ | ✅ | ✅ | ✅ |
| **Hyperliquid** | ✅ | ✅ | ✅ | 공개 API 없음 |
| **Kraken** | ✅ | ✅ | ✅ | 공개 API 없음 |

### 3. 지지 · 저항 + 롱/숏 시나리오
- 주요 레벨
- 진입가 · 손절 · 익절1 · 익절2 · R:R · 신뢰도

---

## 로컬에서 켜기

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

브라우저에서 → [http://localhost:8000](http://localhost:8000)

끝. API 키 없어도 됩니다. (공개 REST만 씀)

---

## Railway에 올리기

이미 `Dockerfile` + `railway.toml` 넣어 뒀어요.

1. 이 레포 연결
2. Root Directory = `crypto-ls-analyzer` (모노레포면)
3. Deploy
4. 커피 한 잔 ☕

`PORT` 는 Railway가 알아서 줍니다.

---

## API (심심하면)

| 경로 | 설명 |
|---|---|
| `GET /api/health` | 살아 있니? |
| `GET /api/analyze` | BTC·ETH·XRP 한 방에 |
| `GET /api/analyze?refresh=true` | 캐시 무시하고 새로 |
| `GET /api/analyze/BTC` | 코인 하나만 |

캐시 TTL ≈ **45초** (거래소 rate limit 예의)

---

## 폴더 구조

```
crypto-ls-analyzer/
├── app/
│   ├── main.py              # FastAPI 입구
│   └── services/
│       ├── binance.py       # 바이낸스
│       ├── exchanges.py     # HL + Kraken + 묶음
│       ├── analysis.py      # 비율 · 레벨
│       └── strategy.py      # 진입 / SL / TP
├── static/                  # 프론트 (바닐라 JS)
├── Dockerfile
└── requirements.txt
```

거창한 프론트 프레임워크 없음.  
HTML + CSS + JS. 가볍고 빠른 맛.

---

## 기술 스택

- **Backend:** FastAPI · httpx · uvicorn  
- **Frontend:** 바닐라 JS (의존성 0개 프론트)  
- **데이터:** Binance · Hyperliquid · Kraken Futures 공개 API  

---

## 연락

| | |
|---|---|
| 👤 | 이영찬 · Young Chan Lee |
| 💬 | Kakao `caramel112` |
| ✉️ | [caramel2516@naver.com](mailto:caramel2516@naver.com) |
| 💼 | [LinkedIn](https://www.linkedin.com/in/young-chan-lee-9304a3287/) (로그인돼 있으면 잘 열려요) |

---

## 면책 (진지 모드 한 줄)

본 프로젝트는 금융 투자 권유가 아니며,  
사용으로 인한 손실에 대해 책임지지 않습니다.  
항상 본인 리스크 관리하세요. 🙏

---

Made with ☕ and mild market anxiety  
by **이영찬**
