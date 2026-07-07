export interface Slide {
  index: number;
  headline: string;
  body: string;
  layout: string;
  graphic: string;
  design_point: string;
}

export interface GenerateRequest {
  topic: string;
  target?: string;
  goal?: string;
  tone?: string;
  cta?: string;
  slide_count: number;
}

export interface GenerateResponse {
  slides: Slide[];
  meta: Record<string, unknown>;
}

export interface CardNews {
  id?: string;
  topic: string;
  slides: Slide[];
  meta?: Record<string, unknown>;
}
