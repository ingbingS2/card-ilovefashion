export interface RankItem {
  mall: "musinsa" | "cm29";
  product_id: string;
  rank: number;
  brand: string;
  name: string;
  price: number | null;
  original_price: number | null;
  discount_rate: number | null;
  review_score: number | null;
  review_count: number | null;
  thumbnail: string | null;
  product_url: string;
  category_code: string | null;
  category_name: string | null;
}

export interface RankingDoc {
  updatedAt: string;
  items: RankItem[];
}

export interface Review {
  score: number | null;
  text: string;
  date: string | null;
  likes: number | null;
}

export interface HistoryPoint {
  t: string;
  rank: number | null;
  price: number | null;
  review_score: number | null;
  review_count: number | null;
}

export interface ProductDoc extends RankItem {
  reviews: Review[];
  history: HistoryPoint[];
  updatedAt: string;
}
