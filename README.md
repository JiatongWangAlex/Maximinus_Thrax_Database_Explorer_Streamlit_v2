## Dataset Licensing

The database and dataset structure of maximinus_thrax.db are © 2026 Jiatong Wang. 

This dataset is made available under the **Creative Commons Attribution 4.0 International License (CC BY 4.0)**. 

* **What this means:** You are free to share, copy, and adapt the records or schema for any purpose, provided you give appropriate credit by citing this project.

The data in itinere_land_roads_optimized.json is derived from the data published by the Itiner-e project; all rights and credits go to them.

The roman provinces polygons in roman_provinces.json are created by me based on coastline data from the Ancient World Mapping Center and province border data for 200 CE from the Digital Atalas of the Roman Empire; all rights and credits go to them.


## Software Disclaimer

AI/LLM USE DISCLAIMER: The dataset and data structure queried by this GUI is FULLY HUMAN MADE AND HUMAN DESIGNED as part of my BA thesis.

I have designed the webapp's layout and logic & created features tailored to my dataset, without AI/LLM input. I have also written the SQL queries used in the backend of this software and coded most of the elements which only involve native Streamlit features.



HOWEVER, as I am not a CS student and this is not a CS thesis, I accepted input from a LLM when debugging and implementing this software, specifically for managing Streamlit session states correctly and injecting the JavaScript and HTML snippets that introduce behaviors not native to Streamlit.
(These parts of the code are responsible for clearing user input after every search, and scrolling users down to the Results viewer or Map viewer automatically after every search).

I have extensively tested the behavior of this Webapp myself; I believe it does execute all queries as I intended.

That said, if you would like to be extra sure, please download the database and query list, and query directly inside 
your SQL database browser. 

Terms of Use: This user interface code is provided "as-is" for sharing, copying, and modification. I assume no liability for any issues or damages arising from its use. Because this is a read-only interface, it does not modify backend data; however, any subsequent reuse or modification of this code is entirely at the user's own risk.


## The full documentation for this project is being prepared
