# How RAG Works

A large language model knows a lot. But it does not know your documents.

RAG fixes this problem. RAG means Retrieval-Augmented Generation.

It works in five steps.

First, you cut your documents into small pieces. Each piece is called a chunk.

Second, you turn each chunk into a list of numbers. This list is called an embedding. It captures the meaning of the text.

Third, you store all embeddings in a special database. This database finds similar meanings fast. It is called a vector database.

Fourth, a user asks a question. You turn the question into an embedding too. Then you search the database for the closest chunks.

Fifth, you give the question and the chunks to the language model. The model writes an answer based on your documents. Not based on its memory.

The result is an answer you can trust. It comes from your data.
