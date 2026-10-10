use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocumentChunk {
    pub id: String,
    pub source: String,
    pub page_number: usize,
    pub text: String,
    pub score: f64,
}

#[derive(Default)]
pub struct VectorStore {
    chunks: Vec<(DocumentChunk, HashMap<String, f64>)>,
}

impl VectorStore {
    pub fn new() -> Self {
        Self::default()
    }

    fn tokenize(text: &str) -> HashMap<String, f64> {
        let mut tf = HashMap::new();
        let words: Vec<String> = text
            .to_lowercase()
            .split(|c: char| !c.is_alphanumeric())
            .filter(|w| w.len() > 1)
            .map(|w| w.to_string())
            .collect();

        let total = words.len() as f64;
        if total == 0.0 {
            return tf;
        }

        for w in words {
            *tf.entry(w).or_insert(0.0) += 1.0 / total;
        }
        tf
    }

    pub fn add_document(&mut self, source: &str, pages: Vec<(usize, String)>) {
        for (page_num, text) in pages {
            // Split into 500-char overlapping chunks
            let char_vec: Vec<char> = text.chars().collect();
            let chunk_size = 500;
            let overlap = 100;
            let mut start = 0;
            let mut chunk_idx = 1;

            while start < char_vec.len() {
                let end = (start + chunk_size).min(char_vec.len());
                let chunk_str: String = char_vec[start..end].iter().collect();

                let id = format!("{}_p{}_c{}", source, page_num, chunk_idx);
                let tf = Self::tokenize(&chunk_str);

                let chunk = DocumentChunk {
                    id,
                    source: source.to_string(),
                    page_number: page_num,
                    text: chunk_str,
                    score: 0.0,
                };

                self.chunks.push((chunk, tf));

                if end == char_vec.len() {
                    break;
                }
                start += chunk_size - overlap;
                chunk_idx += 1;
            }
        }
    }

    pub fn search(&self, query: &str, top_k: usize) -> Vec<DocumentChunk> {
        let q_tf = Self::tokenize(query);
        if q_tf.is_empty() {
            return Vec::new();
        }

        let mut scored: Vec<DocumentChunk> = self
            .chunks
            .iter()
            .map(|(chunk, doc_tf)| {
                let mut score = 0.0;
                for (term, q_weight) in &q_tf {
                    if let Some(doc_weight) = doc_tf.get(term) {
                        score += q_weight * doc_weight * 100.0;
                    }
                }
                let mut c = chunk.clone();
                c.score = score;
                c
            })
            .filter(|c| c.score > 0.0)
            .collect();

        scored.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        scored.truncate(top_k);
        scored
    }
}
