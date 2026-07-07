import { forwardRef } from "react";
import type { Slide } from "../types";

interface Props {
  slide: Slide;
}

// 4:5 (1080x1350) 비율 카드. 내보내기 시 실제 1080x1350 로 렌더된다.
const SlideCard = forwardRef<HTMLDivElement, Props>(({ slide }, ref) => {
  return (
    <div className="slide-card" ref={ref}>
      <div className="slide-index">{slide.index}장</div>
      <h2 className="slide-headline">{slide.headline}</h2>
      {slide.body && <p className="slide-body">{slide.body}</p>}
    </div>
  );
});

SlideCard.displayName = "SlideCard";

export default SlideCard;
