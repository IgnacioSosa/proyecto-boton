import sqlite3
import sys
import os

# Agregar el directorio del proyecto al path para importar módulos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.database import get_connection

def eliminar_tecnicos_no_procesados():
    """Elimina los técnicos específicos que no pudieron ser procesados"""
    
    # Lista de técnicos a eliminar (exactamente como aparecen en tu lista)
    tecnicos_a_eliminar = [
        "Carla Garcia",
        "Nan", 
        "carla garcia",
        "Marcos Alvares",
        "Carla Sosa",
        "carla alvares",
        "None None"
    ]
    
    conn = get_connection()
    c = conn.cursor()
    
    eliminados = []
    no_encontrados = []
    registros_eliminados_total = 0
    
    try:
        print("🔍 Buscando técnicos a eliminar...\n")
        
        for nombre in tecnicos_a_eliminar:
            # Buscar el técnico por nombre exacto
            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (nombre,))
            result = c.fetchone()
            
            if result:
                tecnico_id = result[0]
                
                # Verificar cuántos registros tiene asociados
                c.execute("SELECT COUNT(*) FROM registros WHERE id_tecnico = ?", (tecnico_id,))
                registro_count = c.fetchone()[0]
                
                # Eliminar registros asociados primero
                if registro_count > 0:
                    c.execute("DELETE FROM registros WHERE id_tecnico = ?", (tecnico_id,))
                    registros_eliminados_total += registro_count
                    print(f"🗑️  Eliminados {registro_count} registros del técnico '{nombre}'")
                
                # Eliminar el técnico
                c.execute("DELETE FROM tecnicos WHERE id_tecnico = ?", (tecnico_id,))
                eliminados.append((nombre, registro_count))
                print(f"✅ Técnico '{nombre}' eliminado exitosamente")
            else:
                no_encontrados.append(nombre)
                print(f"⚠️  Técnico '{nombre}' no encontrado en la base de datos")
        
        # Confirmar cambios
        conn.commit()
        
        # Mostrar resumen final
        print("\n" + "="*50)
        print("📊 RESUMEN DE ELIMINACIÓN")
        print("="*50)
        print(f"✅ Técnicos eliminados: {len(eliminados)}")
        print(f"🗑️  Total de registros eliminados: {registros_eliminados_total}")
        print(f"⚠️  Técnicos no encontrados: {len(no_encontrados)}")
        
        if eliminados:
            print("\n🎯 Técnicos eliminados exitosamente:")
            for nombre, registros in eliminados:
                if registros > 0:
                    print(f"   - {nombre} (con {registros} registros)")
                else:
                    print(f"   - {nombre} (sin registros)")
        
        if no_encontrados:
            print("\n❌ Técnicos que no se encontraron:")
            for nombre in no_encontrados:
                print(f"   - {nombre}")
        
        print("\n✨ Proceso completado exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la eliminación: {str(e)}")
        return False
    finally:
        conn.close()
    
    return True

def verificar_tecnicos_restantes():
    """Verifica qué técnicos quedan en la base de datos después de la eliminación"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("SELECT COUNT(*) FROM tecnicos")
        total_tecnicos = c.fetchone()[0]
        
        print(f"\n📈 Técnicos restantes en la base de datos: {total_tecnicos}")
        
        if total_tecnicos > 0:
            c.execute("SELECT nombre FROM tecnicos ORDER BY nombre LIMIT 10")
            tecnicos_muestra = c.fetchall()
            print("\n🔍 Muestra de técnicos restantes:")
            for i, (nombre,) in enumerate(tecnicos_muestra, 1):
                print(f"   {i}. {nombre}")
            
            if total_tecnicos > 10:
                print(f"   ... y {total_tecnicos - 10} más")
    
    except Exception as e:
        print(f"❌ Error al verificar técnicos restantes: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Iniciando eliminación de técnicos no procesados...\n")
    
    # Confirmar antes de proceder
    respuesta = input("¿Estás seguro de que quieres eliminar estos técnicos? (s/N): ")
    
    if respuesta.lower() in ['s', 'si', 'sí', 'y', 'yes']:
        if eliminar_tecnicos_no_procesados():
            verificar_tecnicos_restantes()
        else:
            print("❌ La eliminación falló. Revisa los errores anteriores.")
    else:
        print("❌ Operación cancelada por el usuario.")