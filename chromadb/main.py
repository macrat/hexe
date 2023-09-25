import chromadb

client = chromadb.PersistentClient('./db')
collection = client.get_or_create_collection('test')

collection.add(
    documents=['Hello world!', 'This is a test.', 'こんにちは世界'],
    ids=['doc1', 'doc2', 'doc3']
)

print(collection.query(query_texts=['hello jhon!'], n_results=3))
