# AI agents that read papers and create datasets

1. From a query find initial papers using <https://edisonscientific.gitbook.io/edison-cookbook/edison-client> and trajectories like <https://platform.edisonscientific.com/trajectories/2e8d7bbb-8cb9-4b7d-b94a-2e34c8254c59>
2. Pass these papers to a LLM to create a dataset draft.
3. Search for these papers in a graph using <https://docs.openalex.org/> or similar, find latest papers and update the dataset with the new data.
