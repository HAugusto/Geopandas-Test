# Importar bibliotecas necessárias
import geopandas as gpd
import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
from fpdf import FPDF
import pandas as pd
from datetime import datetime
import os

# Configurações do OSMNX
ox.settings.log_console = False
ox.settings.use_cache = True

# Parâmetros do Veículo
AVERAGE_SPEED_KMH = 30
FUEL_CONSUMPTION_PER_KM = 0.1
FUEL_COST_PER_LITER = 5.5

# Definir o nome do lugar e criar o grafo
place_name = "Sudeste, Brasil"
graph = ox.graph_from_place(place_name, network_type='drive', simplify=True)

# Adicionar comprimento das arestas para garantir que todas tenham o atributo 'length'
graph = ox.distance.add_edge_lengths(graph)

# Pontos de referência para rota
POINT_A = (-23.6531797, -46.5313029)  # Coordenadas de A
POINT_B = (-20.0228668,-44.7984994)  # Coordenadas de B

# Função de cálculo de estatísticas
def calculate_route_statistics(graph, route):
    route_gdf = ox.routing.route_to_gdf(graph, route)
    total_distance_km = round(route_gdf["length"].sum() / 1000, 4)
    total_time_min = round((total_distance_km / AVERAGE_SPEED_KMH) * 60, 4)
    fuel_used_liters = round(total_distance_km * FUEL_CONSUMPTION_PER_KM, 4)
    total_fuel_cost = round(fuel_used_liters * FUEL_COST_PER_LITER, 4)
    elevation_gain = round(route_gdf["grade_abs"].sum(), 4) if "grade_abs" in route_gdf.columns else 0

    return {
        "Distância (km)": total_distance_km,
        "Tempo (min)": total_time_min,
        "Custo (R$)": total_fuel_cost,
        "Consumo de Combustível (litros)": fuel_used_liters,
        "Ganho de Elevação (m)": elevation_gain,
    }

# Função para encontrar a rota com base no critério
def find_best_route(graph, point_a, point_b, priority):
    orig_node = ox.distance.nearest_nodes(graph, point_a[1], point_a[0])
    dest_node = ox.distance.nearest_nodes(graph, point_b[1], point_b[0])

    # Adicionar velocidades e tempos de viagem se a prioridade for 'tempo'
    if priority == 'tempo':
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)

    # Definindo a lógica de peso para cada prioridade
    if priority == 'distancia':
        weight = 'length'
    elif priority == 'tempo':
        weight = 'travel_time'
    elif priority == 'combustivel':
        # Peso considerando o comprimento da aresta e a inclinação
        weight = lambda u, v, d: d.get('length', 0) * FUEL_CONSUMPTION_PER_KM + (d.get('grade_abs', 0) / 100) * d.get('length', 0) * FUEL_CONSUMPTION_PER_KM
    elif priority == 'custo':
        # Cálculo do custo total de combustível com base na distância e inclinação
        weight = lambda u, v, d: (d.get('length', 0) * FUEL_CONSUMPTION_PER_KM * FUEL_COST_PER_LITER) + ((d.get('grade_abs', 0) / 100) * d.get('length', 0) * FUEL_CONSUMPTION_PER_KM * FUEL_COST_PER_LITER)
    else:
        raise ValueError("Prioridade inválida. Escolha entre 'distancia', 'tempo', 'combustivel' ou 'custo'.")

    # Garantir que todas as arestas tenham o atributo 'length' com valor padrão de 0
    for u, v, data in graph.edges(data=True):
        data.setdefault('length', 0)

    # Calcular o caminho mais curto com base no peso definido
    return ox.shortest_path(graph, orig_node, dest_node, weight=weight)

# Função para salvar o mapa da rota
def save_route_map(graph, route, filename):
    fig, ax = ox.plot_graph_route(
        graph, route, 
        node_size=0, 
        bgcolor='white', 
        edge_color='blue', 
        route_linewidth=3, 
        show=False
    )

    # Definir os limites de x e y para centralizar o mapa na rota
    route_nodes = [graph.nodes[node] for node in route]
    x_coords = [node['x'] for node in route_nodes]
    y_coords = [node['y'] for node in route_nodes]
    
    # Ajustar os limites para aumentar o zoom
    ax.set_xlim(min(x_coords) - 0.01, max(x_coords) + 0.01)  # Ajuste o valor para controlar o zoom
    ax.set_ylim(min(y_coords) - 0.01, max(y_coords) + 0.01)  # Ajuste o valor para controlar o zoom
    ax.set_title("Rota de A para B | Santo André", fontsize=15)

    fig.savefig(filename, bbox_inches='tight', dpi=300)  # Salvar com o nome fornecido
    plt.close(fig)

# Função para criar gráfico comparativo
def create_comparative_graph(stats_list, criteria):
    df = pd.DataFrame(stats_list)
    df.index = [f"{crit.capitalize()} (km/min/R$)" for crit in criteria]  # Renomear os índices para incluir unidades
    df.plot(kind='bar', figsize=(10, 6), colormap='viridis')
    plt.title("Comparação das Estatísticas de Rotas")
    plt.ylabel("Valores")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('comparative_route_statistics.png')
    plt.close()

# Função para gerar o relatório PDF
def generate_pdf_report(stats_list, route_map_paths, criteria):
    class PDF(FPDF):
        def header(self):
            self.set_font("Arial", "B", 14)
            self.cell(0, 10, "Relatório de Rota", 0, 1, "C")
            self.cell(0, 10, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, "C")
            self.ln(10)

        def chapter_title(self, title):
            self.set_font("Arial", "B", 12)
            self.cell(0, 10, title, 0, 1, "L")
            self.ln(4)

        def add_table(self, df):
            self.set_font("Arial", "B", 12)
            col_widths = [100, 40]
            headers = df.columns.tolist()

            for i, header in enumerate(headers):
                self.cell(col_widths[i], 10, header, 1)
            self.ln()

            self.set_font("Arial", "", 12)
            for i in range(len(df)):
                for j, item in enumerate(df.iloc[i]):
                    self.cell(col_widths[j], 10, str(item), 1)
                self.ln()
                
    pdf = PDF()

    for i, (stats, path, crit) in enumerate(zip(stats_list, route_map_paths, criteria)):
        pdf.add_page()
        pdf.chapter_title(f"Teste: {crit.capitalize()}")  # Título com o critério utilizado
        stats_df = pd.DataFrame(stats.items(), columns=['Estatística', 'Valor'])
        pdf.add_table(stats_df)
        pdf.image(path, x=10, w=190)
    
    # Adicionar o gráfico comparativo
    pdf.add_page()
    pdf.chapter_title("Gráfico Comparativo de Estatísticas")
    pdf.image('comparative_route_statistics.png', x=10, w=190)
    
    pdf.output("relatorio_comparativo_rotas.pdf")

# Cálculo de rotas e estatísticas
criteria = ['distancia', 'tempo', 'combustivel', 'custo']
stats_list = []
route_map_paths = []

for crit in criteria:
    route = find_best_route(graph, POINT_A, POINT_B, priority=crit)
    stats = calculate_route_statistics(graph, route)
    stats_list.append(stats)
    
    # Salvar o mapa da rota com o critério
    map_filename = f'route_map_{crit}.png'
    save_route_map(graph, route, map_filename)
    route_map_paths.append(map_filename)

# Criar gráfico comparativo
create_comparative_graph(stats_list, criteria)

# Gerar o relatório PDF com os mapas das rotas e o gráfico comparativo
generate_pdf_report(stats_list, route_map_paths, criteria)
