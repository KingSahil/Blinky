use blinky_agent::rag::VectorStore;

#[test]
fn test_vector_store_bm25_search() {
    let mut store = VectorStore::new();

    let doc1 = vec![
        (1, "Rust is a multi-paradigm, general-purpose programming language designed for performance and safety, especially safe concurrency.".to_string()),
        (2, "Memory safety is guaranteed without needing a garbage collector by using a borrow checker to validate references at compile time.".to_string()),
    ];

    let doc2 = vec![
        (1, "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.".to_string()),
        (2, "Python dynamically-typed and garbage-collected. It supports multiple programming paradigms.".to_string()),
    ];

    store.add_document("rust_guide.pdf", doc1);
    store.add_document("python_guide.pdf", doc2);

    let results = store.search("borrow checker memory safety", 2);
    assert!(!results.is_empty());
    assert_eq!(results[0].source, "rust_guide.pdf");
    assert!(results[0].text.contains("borrow checker"));

    let py_results = store.search("dynamic typing indentation", 2);
    assert!(!py_results.is_empty());
    assert_eq!(py_results[0].source, "python_guide.pdf");
}
