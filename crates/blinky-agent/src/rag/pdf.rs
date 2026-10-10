use anyhow::{Context, Result};
use std::path::Path;
use tracing::info;

pub struct PdfExtractor;

impl PdfExtractor {
    pub fn extract_text(path: &Path) -> Result<Vec<(usize, String)>> {
        let doc = lopdf::Document::load(path)
            .with_context(|| format!("Failed to load PDF document from {}", path.display()))?;

        let mut pages = Vec::new();
        for (page_num, _page_id) in doc.get_pages() {
            let text = doc.extract_text(&[page_num]).unwrap_or_default();
            let cleaned = text.trim().to_string();
            if !cleaned.is_empty() {
                pages.push((page_num as usize, cleaned));
            }
        }

        info!(
            "Extracted {} page(s) from PDF {}",
            pages.len(),
            path.display()
        );
        Ok(pages)
    }
}
