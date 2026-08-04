// 카드뉴스 주제 후보 — 국내외 패션 매체에서 확인한 트렌드를 카드에 쓸 수 있는 형태로 정리한 것.
//
// 왜 파일로 관리하나:
//   "요즘 유행"은 크롤 데이터에 없다(몰 랭킹은 판매량이지 유행의 근거가 아니고,
//   인스타 탐색 탭은 개인화 피드라 API 로 읽을 수 없다). 그래서 매체 기사를 근거로
//   사람이 큐레이션한 목록을 여기에 두고, 대시보드 상단에서 고르게 한다.
//
// 규칙 (KEYWORD-POLICY.md):
//   - 랭킹 키워드(랭킹픽·TOP·베스트) 금지. label 은 항상 시즌성 키워드로 쓴다.
//   - `note` 는 카드 정보 블록의 씨앗이다. 반드시 출처(`sources`)로 뒷받침되는 내용만 쓴다.
//   - 갱신 시점이 지나면 stale 하다. `reviewedAt` 을 보고 다시 리서치할 것.

export const TOPICS_REVIEWED_AT = "2026-08-04";

export type TopicSource = { name: string; url: string };

export type Topic = {
  /** 파이프라인에 넘기는 주제 문자열 = 결과 폴더명이 된다 (`카드뉴스\YYYYMMDD <label>`) */
  id: string;
  label: string;
  /** 지금 바로 쓸 수 있는지, 초가을용인지 */
  timing: "지금" | "초가을";
  /** 카드 정보 블록의 씨앗 — 왜 이게 지금 보이는지 한 줄 */
  note: string;
  /** 어느 랭킹 탭에서 상품을 고르면 되는지 (무신사 탭 label 기준) */
  where: string[];
  sources: TopicSource[];
};

const VOGUE_SS: TopicSource = {
  name: "보그 코리아 — 2026 봄/여름 핵심 트렌드",
  url: "https://www.vogue.co.kr/2026/01/06/%ED%8C%A8%EC%85%98-%EC%9C%84%ED%81%AC%EC%97%90%EC%84%9C-%ED%99%95%EC%9D%B8%ED%95%9C-2026-%EB%B4%84-%EC%97%AC%EB%A6%84-%ED%95%B5%EC%8B%AC-%ED%8A%B8%EB%A0%8C%EB%93%9C-12%EA%B0%80%EC%A7%80/",
};
const WWW_FALL: TopicSource = {
  name: "Who What Wear — 8 Fashion Trends We're Buying for Fall 2026",
  url: "https://www.whowhatwear.com/fashion/shopping/fall-2026-fashion-trends",
};
const WWW_TRANSITION: TopicSource = {
  name: "Who What Wear — Summer-to-Fall Transition",
  url: "https://www.whowhatwear.com/fashion/luxury/summer-to-fall-transitional-luxury-shopping-2026",
};
const FASHION_MAG: TopicSource = {
  name: "FASHION Magazine — Top 10 Trends From the Fall 2026 Runways",
  url: "https://fashionmagazine.com/style/fall-2026-trends/",
};
const MUSINSA_TREND: TopicSource = {
  name: "무신사 — 지금 알아야 할 2026 패션 트렌드",
  url: "https://www.musinsa.com/content/1460916785052579323",
};

export const TOPICS: Topic[] = [
  {
    id: "late-summer-clog",
    label: "늦여름 클로그",
    timing: "지금",
    note: "브랜드마다 굽 높이와 코 모양을 다르게 변주하면서 올여름 잇 아이템으로 올라선 실루엣. 양말을 신으면 초가을까지 이어서 신는다.",
    where: ["신발"],
    sources: [VOGUE_SS],
  },
  {
    id: "white-long-sleeve",
    label: "환절기 흰 긴소매",
    timing: "지금",
    note: "여름 내내 인기였던 긴소매 흰 티가 가을까지 그대로 이어진다. 레이어드를 시작하는 가장 단순한 기준점이라 한 장 사두면 계절을 넘긴다.",
    where: ["상의"],
    sources: [WWW_FALL, WWW_TRANSITION],
  },
  {
    id: "polka-dot",
    label: "늦여름 도트",
    timing: "지금",
    note: "도트가 돌아왔는데 예전의 귀여운 잔물방울이 아니다. 흑백 대비가 강한 큰 점, 시스루 소재와 겹쳐 입는 방식으로 분위기가 완전히 바뀌었다.",
    where: ["원피스/스커트", "상의"],
    sources: [FASHION_MAG],
  },
  {
    id: "v-neck",
    label: "환절기 브이넥",
    timing: "지금",
    note: "같은 네크라인으로 계절을 넘기는 방식. 더울 땐 브이넥 탱크로, 선선해지면 같은 라인의 니트로 갈아탄다. 환절기에 옷장이 어색해지지 않는 이유.",
    where: ["상의"],
    sources: [WWW_FALL],
  },
  {
    id: "dark-denim",
    label: "초가을 다크 데님",
    timing: "초가을",
    note: "밝은 워싱 자리를 인디고가 대신한다. 같은 청바지인데 진한 색 하나로 정돈돼 보이는 게 핵심이라, 여름 상의에 먼저 물려 입기 좋다.",
    where: ["바지"],
    sources: [WWW_FALL],
  },
  {
    id: "check-plaid",
    label: "초가을 체크",
    timing: "초가을",
    note: "여름 프린트가 빠진 자리를 체크와 플레이드가 채운다. 가을이 왔다는 걸 가장 먼저 알리는 패턴이라 8월 말부터 눈에 띄기 시작한다.",
    where: ["상의", "원피스/스커트"],
    sources: [WWW_FALL],
  },
  {
    id: "scarlet-red",
    label: "가을까지 가는 레드",
    timing: "초가을",
    note: "봄여름 런웨이의 스칼렛이 가을까지 그대로 이어지는 드문 컬러. 토마토빛 붉은색 하나만 걸쳐도 계절이 바뀐 티가 난다.",
    where: ["상의", "아우터", "가방"],
    sources: [VOGUE_SS, FASHION_MAG],
  },
  {
    id: "quarter-zip",
    label: "초가을 쿼터집",
    timing: "초가을",
    note: "안에 뭘 받쳐 입느냐로 완전히 달라지는 아이템. 셔츠를 넣으면 단정해지고 스트라이프를 넣으면 캐주얼해져서, 한 장으로 여러 벌처럼 쓴다.",
    where: ["상의", "아우터"],
    sources: [MUSINSA_TREND],
  },
];
