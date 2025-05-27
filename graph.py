from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langgraph.graph import START, END, StateGraph
from langgraph.types import Send
from schemas import *
from prompts import *
from tavily import TavilyClient
from dotenv import load_dotenv
import streamlit as st
import os
load_dotenv()

llm = ChatOpenAI(model="gpt-4o")


def build_first_queries(state: ReportState): 
    class QueryList(BaseModel):
        queries: List[str]
        
    user_input = state.user_input

    prompt = build_queries.format(user_input=user_input)
    query_llm = llm.with_structured_output(QueryList)
    result = query_llm.invoke(prompt)

    return {"queries": result.queries}


def spawn_researchers(state: ReportState):
    return [Send("single_search",query) for query in state.queries]


def single_search(query: str):
    tavily_client = TavilyClient()

    results = tavily_client.search(query, 
                         max_results=1, 
                         include_raw_content=False)

    query_results = []
    for result in results["results"]:
        url = result["url"]
        url_extraction = tavily_client.extract(url)

        if len(url_extraction["results"]) > 0:
            raw_content = url_extraction["results"][0]["raw_content"]
            prompt = resume_search.format(user_input=user_input,
                                        search_results=raw_content)

            llm_result = llm.invoke(prompt)
            query_results += [QueryResult(title=result["title"],
                                    url=url,
                                    resume=llm_result.content)]
    return {"queries_results": query_results}

def final_writer(state: ReportState):
    search_results = ""
    references = ""
    for i, result in enumerate(state.queries_results):
        search_results += f"[{i+1}]\n\n"
        search_results += f"Title: {result.title}\n"
        search_results += f"URL: {result.url}\n"
        search_results += f"Content: {result.resume}\n"
        search_results += f"================\n\n"

        references += f"[{i+1}] - [{result.title}]({result.url})\n"
    

    prompt = build_final_response.format(user_input=user_input,
                                    search_results=search_results)

  
    llm_result = llm.invoke(prompt)

    print(llm_result)
    final_response = llm_result.content + "\n\n References:\n" + references
    

    return {"final_response": final_response}



builder = StateGraph(ReportState)

builder.add_node("build_first_queries",build_first_queries)
builder.add_node("single_search",single_search)
builder.add_node("final_writer",final_writer)

builder.add_edge(START, "build_first_queries")
builder.add_conditional_edges("build_first_queries",
                              spawn_researchers,
                              ["single_search"])
builder.add_edge("single_search","final_writer")
builder.add_edge("final_writer",END)
graph = builder.compile()

if __name__ == "__main__":
    st.title("Project 1 - Nelson Neto")
    user_input = st.text_input("What is your question?", 
                               value="")

    if st.button("Pesquisar"):
        
        with st.status("Gerando resposta"):
            for output in graph.stream({"user_input": user_input},
                                        stream_mode="debug"
                                        # stream_mode="messages"
                                        ):
                if output["type"] == "task_result":
                    st.write(f"Running {output['payload']['name']}")
                    st.write(output)
        response = output["payload"]["result"][0][1]

        st.write(response)
