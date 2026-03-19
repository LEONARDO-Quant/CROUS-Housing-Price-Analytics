<p align="center">
  <img src="docs/banner.webp" alt="Bannière du projet" width="1000" height="250"/>
</p>

#  CROUS Housing: A Data-Driven Study of the S2 Residual Market 📊

This project delivers a comprehensive analysis of the student housing market in France, specifically focusing on the under-documented **second semester (S2)**. 
By leveraging web scraping and statistical modeling, we provide insights into price disparities and market anomalies for mid-year student mobility.

##  Data Science Workflow 🛠️

### 1. Data Engineering (Scraping)
A modular and robust scraping engine was developed using **Python (BeautifulSoup, Requests)**:
* **Systematic Collection**: Automated extraction of 4,000+ raw listings to isolate a clean dataset of **296 active S2 offers**.
* **Resilience**: Implementation of `try/except` blocks and systematic delays to ensure high-quality data recovery and server politeness.
* **Data Cleaning**: Standardization of addresses, prices, and surfaces into a structured **Pandas** DataFrame.

### 2. Quantitative Analysis
Focusing on the **Price per $m^{2}$** as the primary performance indicator:
* **Correlation Matrix**: Revealed a strong negative correlation (**-0.77**) between surface area and price per $m^{2}$, demonstrating significant economies of scale.
* **Market Inversion**: Identified a counter-intuitive peak in **Brittany** (€29.4/$m^{2}$) versus **Île-de-France** (€9.25/$m^{2}$), highlighting the specific "residual" nature of the S2 supply.
* **Feature Engineering**: Created 4 new variables, including enriched localization and price metrics, to refine the comparative analysis.

##  Key Findings 📈
* **Median Price**: Established at **19.93 €/$m^{2}$** for the S2 period.
* **Market Insight**: Total rent shows a near-zero correlation (**-0.02**) with price per $m^{2}$, proving that total cost is an insufficient metric for value comparison.
* **Regional Tensions**: The Grand Est region offers the highest volume of residual housing, whereas Centre-Val de Loire remains the most constrained.

##  Future Roadmap 🚀
* **Predictive Modeling**: Implement multivariate regressions to quantify the impact of "housing type" (Studio vs. T1) on pricing.
* **Longitudinal Tracking**: Automate seasonal comparisons (S1 vs. S2) to build a permanent student housing observatory.
