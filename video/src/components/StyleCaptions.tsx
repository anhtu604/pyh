import React from 'react';
import {useCurrentFrame} from 'remotion';
import {useLayout} from '../layout';
import {hexToRgba, formatOf, pyhCaptions, pyhColors, pyhStroke, pyhType} from '../style/pyhStyle';
import {evenWordTiming, firstUseTermWords, paginateCaptions, pageAtFrame, type TimedWord} from './captionPaging';

export type StyleCaptionsProps = {
  text: string;
  durationInFrames: number;
  words?: readonly TimedWord[];
  /** Terms already labelled on the diagram; highlighted yellow on first use. */
  glossary?: readonly string[];
  /** Draw the off_white 90% band behind the text (default true). */
  band?: boolean;
  previousText?: string;
  labelWindows?: readonly {term: string; start: number; end: number}[];
};

export const StyleCaptions: React.FC<StyleCaptionsProps> = ({text, durationInFrames, words: timed, glossary = [], band = true, previousText = '', labelWindows}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const format = formatOf(layout);
  const c = layout.captions;
  const limits = pyhCaptions[format];
  const words: TimedWord[] = timed?.length ? [...timed]
    : evenWordTiming(text, 0, Math.max(1, durationInFrames / Math.max(1, text.trim().split(/\s+/).length)), 0)
      .map((w, i, all) => ({...w, end_frame: i + 1 < all.length ? all[i + 1].start_frame : durationInFrames}));
  const plain = words.map((w) => w.text);
  const pages = paginateCaptions(plain, limits.maxCharsPerLine, limits.maxLines);
  const page = pageAtFrame(pages, words, frame);
  const prior = previousText.trim().split(/\s+/).filter(Boolean);
  const pageIndices = page?.lines.flat().map((w) => w.index) ?? [];
  const pageStart = words[pageIndices[0]]?.start_frame ?? 0;
  const pageEnd = words[(pageIndices.at(-1) ?? -1) + 1]?.start_frame ?? durationInFrames;
  // Fix the choice per page; changing the label cannot select a second yellow phrase.
  const candidates = glossary.flatMap((term) => {
    if (firstUseTermWords(prior, [term]).size) return [];
    const indices = [...firstUseTermWords(plain, [term])];
    if (!indices.length || !page?.lines.some((line) => indices.every((i) => line.some((w) => w.index === i)))) return [];
    if (labelWindows && !labelWindows.some((w) => w.term.toLowerCase() === term.toLowerCase()
      && w.start <= pageStart && w.end >= pageEnd)) return [];
    return [{term, indices}];
  });
  const chosen = candidates[0];
  const termWords = new Set(chosen?.indices ?? []);
  const fontSize = c.fontSize;
  return <div data-style-captions="true" data-format={format} aria-label="Phụ đề đang đọc"
    style={{position: 'absolute', left: c.left, bottom: c.bottom, width: c.width, height: c.height,
      boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
      backgroundColor: band ? hexToRgba(pyhColors.background, pyhCaptions.bandOpacity) : undefined,
      borderRadius: pyhStroke.radius, fontFamily: pyhType.fontFamily, fontSize, lineHeight: 1.3,
      fontWeight: pyhType.bodyWeight, color: pyhColors.ink, textAlign: 'center'}}>
    {page?.lines.map((line) => <div key={line[0].index} data-caption-line="true" style={{whiteSpace: 'nowrap'}}>
      {groupTerms(line, termWords).map((group) => {
        const words = group.words.map((w, i) => {
          return <React.Fragment key={w.index}>{i > 0 ? ' ' : null}
            <span data-word={w.index} data-term={group.term ? 'true' : undefined}
              style={{color: pyhColors.ink, fontWeight: pyhType.bodyWeight}}>{w.text}</span>
          </React.Fragment>;
        });
        const lead = group.start > 0 ? ' ' : null;
        return <React.Fragment key={group.words[0].index}>{lead}
          {group.term ? <span data-term-group="true" style={{backgroundColor: pyhColors.alert, borderRadius: 8, padding: '0 10px'}}>{words}</span> : words}
        </React.Fragment>;
      })}
    </div>)}
  </div>;
};

type Group = {term: boolean; start: number; words: {index: number; text: string}[]};
/** Consecutive glossary words share one continuous yellow band. */
const groupTerms = (line: {index: number; text: string}[], terms: ReadonlySet<number>): Group[] => {
  const groups: Group[] = [];
  line.forEach((word, position) => {
    const term = terms.has(word.index);
    const last = groups[groups.length - 1];
    if (last && last.term === term) last.words.push(word);
    else groups.push({term, start: position, words: [word]});
  });
  return groups;
};
