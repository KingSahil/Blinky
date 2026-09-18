import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface MarkdownRendererProps {
  content: string;
  isUser?: boolean;
}

// Convert common LaTeX math commands and symbols to clean Unicode math notation
function parseLatexToUnicode(tex: string): string {
  let res = tex;

  // Greek letters
  const greek: Record<string, string> = {
    '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ', '\\epsilon': 'ε',
    '\\zeta': 'ζ', '\\eta': 'η', '\\theta': 'θ', '\\iota': 'ι', '\\kappa': 'κ',
    '\\lambda': 'λ', '\\mu': 'μ', '\\nu': 'ν', '\\xi': 'ξ', '\\pi': 'π',
    '\\rho': 'ρ', '\\sigma': 'σ', '\\tau': 'τ', '\\upsilon': 'υ', '\\phi': 'φ',
    '\\chi': 'χ', '\\psi': 'ψ', '\\omega': 'ω',
    '\\Gamma': 'Γ', '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ', '\\Xi': 'Ξ',
    '\\Pi': 'Π', '\\Sigma': 'Σ', '\\Upsilon': 'Υ', '\\Phi': 'Φ', '\\Psi': 'Ψ', '\\Omega': 'Ω',
  };
  for (const [cmd, sym] of Object.entries(greek)) {
    res = res.replaceAll(cmd, sym);
  }

  // Math operators and relations
  const ops: Record<string, string> = {
    '\\pm': '±', '\\times': '×', '\\div': '÷', '\\cdot': '·',
    '\\leq': '≤', '\\geq': '≥', '\\neq': '≠', '\\approx': '≈',
    '\\equiv': '≡', '\\infty': '∞', '\\in': '∈', '\\notin': '∉',
    '\\subset': '⊂', '\\subseteq': '⊆', '\\cup': '∪', '\\cap': '∩',
    '\\rightarrow': '→', '\\leftarrow': '←', '\\Rightarrow': '⇒', '\\Leftarrow': '⇐',
    '\\Leftrightarrow': '⇔', '\\forall': '∀', '\\exists': '∃', '\\nabla': '∇',
    '\\partial': '∂', '\\sum': '∑', '\\prod': '∏', '\\int': '∫',
    '\\circ': '°', '\\degree': '°', '\\dots': '…', '\\cdots': '⋯',
  };
  for (const [cmd, sym] of Object.entries(ops)) {
    res = res.replaceAll(cmd, sym);
  }

  // Fractions: \frac{a}{b} -> (a / b)
  res = res.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '($1 / $2)');

  // Square roots: \sqrt{x} -> √(x)
  res = res.replace(/\\sqrt\{([^}]+)\}/g, '√($1)');

  // Superscripts and subscripts
  const supers: Record<string, string> = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'n': 'ⁿ', 'i': 'ⁱ', 'x': 'ˣ', 'y': 'ʸ',
  };
  const subs: Record<string, string> = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    'a': 'ₐ', 'e': 'ₑ', 'i': 'ᵢ', 'o': 'ₒ', 'r': 'ᵣ', 'u': 'ᵤ', 'v': 'ᵥ', 'x': 'ₓ',
  };

  res = res.replace(/\^([0-9+\-nixy])/g, (_, ch) => supers[ch] || `^${ch}`);
  res = res.replace(/\^\{([^}]+)\}/g, (_, inner) => {
    return inner.split('').map((c: string) => supers[c] || c).join('');
  });

  res = res.replace(/_([0-9+\-aeioruvx])/g, (_, ch) => subs[ch] || `_${ch}`);
  res = res.replace(/_\{([^}]+)\}/g, (_, inner) => {
    return inner.split('').map((c: string) => subs[c] || c).join('');
  });

  // Clean text commands like \text{...} or \mathrm{...}
  res = res.replace(/\\(text|mathrm|mathbf)\{([^}]+)\}/g, '$2');

  return res.trim();
}

// Render formatted inline spans (bold, italic, code, links, inline latex)
function renderInlineSpans(text: string, isUser: boolean = false): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // 1. Inline LaTeX Math: $...$ or \(...\)
    const mathMatch = remaining.match(/^(\$([^\$]+)\$|\\\((.+?)\\\))/);
    if (mathMatch) {
      const tex = mathMatch[2] || mathMatch[3] || '';
      const unicodeMath = parseLatexToUnicode(tex);
      nodes.push(
        <Text key={`math-${key++}`} style={styles.inlineMathText}>
          {unicodeMath}
        </Text>
      );
      remaining = remaining.slice(mathMatch[0].length);
      continue;
    }

    // 2. Inline Code: `...`
    const codeMatch = remaining.match(/^`([^`]+)`/);
    if (codeMatch) {
      nodes.push(
        <Text key={`code-${key++}`} style={styles.inlineCodeBadge}>
          {` ${codeMatch[1]} `}
        </Text>
      );
      remaining = remaining.slice(codeMatch[0].length);
      continue;
    }

    // 3. Bold + Italic: ***...*** or ___...___
    const boldItalicMatch = remaining.match(/^(\*\*\*|___)(.+?)\1/);
    if (boldItalicMatch) {
      nodes.push(
        <Text key={`bi-${key++}`} style={[styles.inlineBoldText, styles.inlineItalicText]}>
          {boldItalicMatch[2]}
        </Text>
      );
      remaining = remaining.slice(boldItalicMatch[0].length);
      continue;
    }

    // 4. Bold: **...** or __...__
    const boldMatch = remaining.match(/^(\*\*|__)(.+?)\1/);
    if (boldMatch) {
      nodes.push(
        <Text key={`b-${key++}`} style={styles.inlineBoldText}>
          {boldMatch[2]}
        </Text>
      );
      remaining = remaining.slice(boldMatch[0].length);
      continue;
    }

    // 5. Italic: *...* or _..._
    const italicMatch = remaining.match(/^(\*|_)(.+?)\1/);
    if (italicMatch) {
      nodes.push(
        <Text key={`i-${key++}`} style={styles.inlineItalicText}>
          {italicMatch[2]}
        </Text>
      );
      remaining = remaining.slice(italicMatch[0].length);
      continue;
    }

    // 6. Markdown Link: [title](url)
    const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/);
    if (linkMatch) {
      const label = linkMatch[1];
      const url = linkMatch[2];
      nodes.push(
        <Text
          key={`link-${key++}`}
          style={styles.inlineLinkText}
          onPress={() => {
            if (url.startsWith('http://') || url.startsWith('https://')) {
              Linking.openURL(url).catch(() => {});
            }
          }}
        >
          {label}
        </Text>
      );
      remaining = remaining.slice(linkMatch[0].length);
      continue;
    }

    // 7. Plain text chunk up to the next potential token
    const nextSpecial = remaining.search(/[\$`\*_\[\\]/);
    if (nextSpecial === -1) {
      nodes.push(
        <Text key={`text-${key++}`} style={isUser ? styles.userPlainText : styles.blinkyPlainText}>
          {remaining}
        </Text>
      );
      break;
    } else if (nextSpecial > 0) {
      nodes.push(
        <Text key={`text-${key++}`} style={isUser ? styles.userPlainText : styles.blinkyPlainText}>
          {remaining.slice(0, nextSpecial)}
        </Text>
      );
      remaining = remaining.slice(nextSpecial);
    } else {
      // Single unrecognized character
      nodes.push(
        <Text key={`char-${key++}`} style={isUser ? styles.userPlainText : styles.blinkyPlainText}>
          {remaining[0]}
        </Text>
      );
      remaining = remaining.slice(1);
    }
  }

  return nodes;
}

export function MarkdownRenderer({ content, isUser = false }: MarkdownRendererProps) {
  if (!content) return null;

  // Split content into blocks: Code blocks, Display Math blocks, Headers, Lists, Quotes, Tables, Paragraphs
  const blocks: React.ReactNode[] = [];
  const lines = content.split('\n');
  let i = 0;
  let blockKey = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Code Block: ```lang ... ```
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim() || 'code';
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // Skip closing ```

      const codeContent = codeLines.join('\n');
      blocks.push(
        <View key={`codeblock-${blockKey++}`} style={styles.codeBlockCard}>
          <View style={styles.codeBlockHeader}>
            <View style={styles.codeBlockDotRow}>
              <View style={[styles.codeBlockDot, { backgroundColor: '#EF4444' }]} />
              <View style={[styles.codeBlockDot, { backgroundColor: '#F59E0B' }]} />
              <View style={[styles.codeBlockDot, { backgroundColor: '#10B981' }]} />
            </View>
            <Text style={styles.codeBlockLangBadge}>{lang.toUpperCase()}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text style={styles.codeBlockText}>{codeContent}</Text>
          </ScrollView>
        </View>
      );
      continue;
    }

    // 2. Display LaTeX Block: $$ ... $$ or \[ ... \]
    if (trimmed.startsWith('$$') || trimmed.startsWith('\\[')) {
      const mathLines: string[] = [];
      let isSingleLine = false;

      if (trimmed.startsWith('$$') && trimmed.endsWith('$$') && trimmed.length > 4) {
        mathLines.push(trimmed.slice(2, -2).trim());
        isSingleLine = true;
      } else if (trimmed.startsWith('\\[') && trimmed.endsWith('\\]') && trimmed.length > 4) {
        mathLines.push(trimmed.slice(2, -2).trim());
        isSingleLine = true;
      } else {
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('$$') && !lines[i].trim().startsWith('\\]')) {
          mathLines.push(lines[i]);
          i++;
        }
        i++; // Skip closing tag
      }

      if (isSingleLine) {
        i++;
      }

      const tex = mathLines.join(' ');
      const unicodeMath = parseLatexToUnicode(tex);

      blocks.push(
        <View key={`math-block-${blockKey++}`} style={styles.displayMathCard}>
          <Text style={styles.displayMathText}>{unicodeMath}</Text>
        </View>
      );
      continue;
    }

    // 3. Horizontal Rule: --- or ***
    if (/^(\-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push(<View key={`hr-${blockKey++}`} style={styles.horizontalRule} />);
      i++;
      continue;
    }

    // 4. Headers: #, ##, ###, ####
    const h1Match = trimmed.match(/^#\s+(.+)$/);
    if (h1Match) {
      blocks.push(
        <View key={`h1-${blockKey++}`} style={styles.h1Container}>
          <Text style={styles.h1Text}>{renderInlineSpans(h1Match[1], isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    const h2Match = trimmed.match(/^##\s+(.+)$/);
    if (h2Match) {
      blocks.push(
        <View key={`h2-${blockKey++}`} style={styles.h2Container}>
          <Text style={styles.h2Text}>{renderInlineSpans(h2Match[1], isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    const h3Match = trimmed.match(/^###\s+(.+)$/);
    if (h3Match) {
      blocks.push(
        <View key={`h3-${blockKey++}`} style={styles.h3Container}>
          <Text style={styles.h3Text}>{renderInlineSpans(h3Match[1], isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    const h4Match = trimmed.match(/^####\s+(.+)$/);
    if (h4Match) {
      blocks.push(
        <View key={`h4-${blockKey++}`} style={styles.h4Container}>
          <Text style={styles.h4Text}>{renderInlineSpans(h4Match[1], isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    // 5. Blockquote / Alert: > [!NOTE], > [!TIP], > ...
    if (trimmed.startsWith('>')) {
      const quoteText = trimmed.replace(/^>\s*/, '');
      let alertType: 'note' | 'tip' | 'warning' | 'important' | 'quote' = 'quote';
      let alertContent = quoteText;

      if (quoteText.startsWith('[!NOTE]')) {
        alertType = 'note';
        alertContent = quoteText.replace(/^\[!NOTE\]\s*/, '');
      } else if (quoteText.startsWith('[!TIP]')) {
        alertType = 'tip';
        alertContent = quoteText.replace(/^\[!TIP\]\s*/, '');
      } else if (quoteText.startsWith('[!WARNING]')) {
        alertType = 'warning';
        alertContent = quoteText.replace(/^\[!WARNING\]\s*/, '');
      } else if (quoteText.startsWith('[!IMPORTANT]')) {
        alertType = 'important';
        alertContent = quoteText.replace(/^\[!IMPORTANT\]\s*/, '');
      }

      const alertBorderColors = {
        note: '#3B82F6',
        tip: '#10B981',
        warning: '#F59E0B',
        important: '#A855F7',
        quote: '#6C6985',
      };

      blocks.push(
        <View
          key={`quote-${blockKey++}`}
          style={[styles.blockquoteCard, { borderLeftColor: alertBorderColors[alertType] }]}
        >
          {alertType !== 'quote' && (
            <View style={styles.alertHeaderRow}>
              <Ionicons
                name={
                  alertType === 'note' ? 'information-circle' :
                  alertType === 'tip' ? 'bulb' :
                  alertType === 'warning' ? 'warning' : 'star'
                }
                size={14}
                color={alertBorderColors[alertType]}
                style={{ marginRight: 5 }}
              />
              <Text style={[styles.alertTitle, { color: alertBorderColors[alertType] }]}>
                {alertType.toUpperCase()}
              </Text>
            </View>
          )}
          <Text style={styles.blockquoteText}>{renderInlineSpans(alertContent, isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    // 6. Unordered List Items: - or *
    const bulletMatch = line.match(/^(\s*)([-*])\s+(.+)$/);
    if (bulletMatch) {
      const indentLevel = Math.min(Math.floor(bulletMatch[1].length / 2), 3);
      const text = bulletMatch[3];
      blocks.push(
        <View
          key={`li-${blockKey++}`}
          style={[styles.listItemRow, { marginLeft: indentLevel * 14 }]}
        >
          <View style={styles.listBulletDot} />
          <Text style={styles.listItemText}>{renderInlineSpans(text, isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    // 7. Numbered List Items: 1. , 2. 
    const numMatch = line.match(/^(\s*)(\d+)\.\s+(.+)$/);
    if (numMatch) {
      const indentLevel = Math.min(Math.floor(numMatch[1].length / 2), 3);
      const num = numMatch[2];
      const text = numMatch[3];
      blocks.push(
        <View
          key={`num-li-${blockKey++}`}
          style={[styles.listItemRow, { marginLeft: indentLevel * 14 }]}
        >
          <Text style={styles.listNumberBadge}>{num}.</Text>
          <Text style={styles.listItemText}>{renderInlineSpans(text, isUser)}</Text>
        </View>
      );
      i++;
      continue;
    }

    // 8. Empty lines
    if (!trimmed) {
      blocks.push(<View key={`spacer-${blockKey++}`} style={styles.paragraphSpacer} />);
      i++;
      continue;
    }

    // 9. Regular Paragraph
    blocks.push(
      <View key={`p-${blockKey++}`} style={styles.paragraphContainer}>
        <Text style={styles.paragraphText}>{renderInlineSpans(trimmed, isUser)}</Text>
      </View>
    );
    i++;
  }

  return <View style={styles.container}>{blocks}</View>;
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  userPlainText: {
    color: '#FFFFFF',
    fontSize: 14.5,
    lineHeight: 22,
  },
  blinkyPlainText: {
    color: '#ECECF1',
    fontSize: 14.5,
    lineHeight: 22,
  },
  paragraphContainer: {
    marginVertical: 2.5,
  },
  paragraphText: {
    fontSize: 14.5,
    lineHeight: 22,
    color: '#ECECF1',
  },
  paragraphSpacer: {
    height: 6,
  },

  // Headers
  h1Container: {
    marginTop: 10,
    marginBottom: 5,
    paddingBottom: 4,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.1)',
  },
  h1Text: {
    fontSize: 19,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 0.3,
  },
  h2Container: {
    marginTop: 9,
    marginBottom: 4,
  },
  h2Text: {
    fontSize: 17,
    fontWeight: '700',
    color: '#F9FAFB',
    letterSpacing: 0.2,
  },
  h3Container: {
    marginTop: 8,
    marginBottom: 3,
  },
  h3Text: {
    fontSize: 15.5,
    fontWeight: '700',
    color: '#E5E7EB',
  },
  h4Container: {
    marginTop: 6,
    marginBottom: 2,
  },
  h4Text: {
    fontSize: 14.5,
    fontWeight: '600',
    color: '#D1D5DB',
  },

  // Inline Spans
  inlineBoldText: {
    fontWeight: '700',
    color: '#FFFFFF',
  },
  inlineItalicText: {
    fontStyle: 'italic',
    color: '#D1D5DB',
  },
  inlineCodeBadge: {
    fontFamily: 'monospace',
    fontSize: 13,
    color: '#F472B6',
    backgroundColor: 'rgba(30, 27, 46, 0.95)',
    paddingHorizontal: 4,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(244, 114, 182, 0.2)',
  },
  inlineMathText: {
    fontFamily: 'monospace',
    fontSize: 14,
    color: '#38BDF8',
    fontWeight: '600',
  },
  inlineLinkText: {
    color: '#60A5FA',
    textDecorationLine: 'underline',
    fontWeight: '500',
  },

  // Code Block
  codeBlockCard: {
    backgroundColor: '#0F0D17',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    marginVertical: 7,
    overflow: 'hidden',
  },
  codeBlockHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.06)',
  },
  codeBlockDotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  codeBlockDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  codeBlockLangBadge: {
    color: '#9CA3AF',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  codeBlockText: {
    fontFamily: 'monospace',
    fontSize: 13,
    color: '#E0E7FF',
    lineHeight: 19,
    padding: 10,
  },

  // Display LaTeX
  displayMathCard: {
    backgroundColor: 'rgba(56, 189, 248, 0.07)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.2)',
    paddingVertical: 10,
    paddingHorizontal: 14,
    marginVertical: 6,
    alignItems: 'center',
  },
  displayMathText: {
    fontFamily: 'monospace',
    fontSize: 16,
    color: '#7DD3FC',
    fontWeight: '600',
    textAlign: 'center',
  },

  // Lists
  listItemRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginVertical: 2,
  },
  listBulletDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#FF5A36',
    marginTop: 8,
    marginRight: 8,
  },
  listNumberBadge: {
    fontSize: 13.5,
    fontWeight: '700',
    color: '#FF5A36',
    marginRight: 6,
    marginTop: 1,
  },
  listItemText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 21,
    color: '#E2E8F0',
  },

  // Blockquote / Alert
  blockquoteCard: {
    borderLeftWidth: 3,
    paddingLeft: 10,
    paddingVertical: 5,
    marginVertical: 5,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    borderRadius: 4,
  },
  alertHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 3,
  },
  alertTitle: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  blockquoteText: {
    fontSize: 13.5,
    lineHeight: 20,
    color: '#CBD5E1',
    fontStyle: 'italic',
  },

  // Horizontal Rule
  horizontalRule: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    marginVertical: 10,
    width: '100%',
  },
});
