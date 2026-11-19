from app.repos import pedidos_repository
from app.repos.catalogos_repository import CatalogosRepository
from app.conexion import Conexion
from sqlalchemy import text
from app.repos.nuevo_pedido_repository import NuevoPedidoRepository
class PedidosService:
    @classmethod
    def obtener_catalogos(cls) -> dict:
        """Obtiene los catálogos necesarios para el formulario."""
        return {
            "proveedores": CatalogosRepository.proveedores(),
            "niveles": CatalogosRepository.niveles_limpieza(),
            "bodegas": CatalogosRepository.bodegas(),
        }


    @classmethod
    def preparar_nuevo(cls) -> dict:
        """
        Prepara el formulario para crear una nueva solicitud.
        No realiza inserciones ni modificaciones en BD.
        """
        datos = cls.obtener_catalogos()

        datos.update({
            "modo": "nuevo",

            # Cabecera del pedido
            "c": {
                "estdo": None,
                "estado": "",
                "prov": "",
                "fped": "",
                "fpac": "",
                "internacional": False,
                "oc": "",
                "lote": "",
                "trm": None,
                "bod": "",
                "reg": "",
            },

            # Producto seleccionado
            "sel": {
                "plu": "",
                "nombre": "",
                "nivel": "",
                "precio": None,
                "us": None,
            },

            # Líneas y resumen
            "lineas": [],
            "bars": [],
            "steps": [],
            "cost": 0,
            "margin": 0,
            "total_iva": 0,
        })

        return datos
    
    @classmethod
    def preparar_consulta(cls, numero_pedido: int) -> dict:
        """Prepara los datos de un pedido para mostrarlo en pantalla."""

        pedido = pedidos_repository.cargar_pedido(numero_pedido)

        if not pedido:
            return None

        cab = pedido["cabecera"]
        lineas = pedido["lineas"]

        datos = cls.obtener_catalogos()

        datos.update({
            "modo": "consulta",

            # Cabecera
            "c": {
                "estdo": cab["estdo"],
                "estado": cab["estado_nombre"],
                "prov": cab["idntfccion"],
                "fped": cab["fcha_pddo"],
                "fpac": cab["fcha_pctda"],
                "internacional": cab["tpo_ped"],
                "oc": cab["nmro_pddo"],
                "lote": cab["lte_int"],
                "trm": cab["trm"],
                "bod": cab["bdga_dstno"],
                "reg": cab["realizado"],
            },

            # Producto seleccionado
            "sel": {
                "plu": "",
                "nombre": "",
                "nivel": "",
                "precio": None,
                "us": None,
            },

            # Líneas del pedido
            "lineas": [
                {
                    "plu": ln["cdgo_plu"],
                    "nombre": ln["nmbre_prdcto"],
                    "bod": ln["lclzcion"],
                    "nivel": ln["tpo_lmpza"],
                    "qty": ln["cntdad_pdda"],
                    "precio": ln["prcio_cmpra"],
                    "us": ln["prcio_mnda"],
                    "sel": False,
                    "url": "#",
                }
                for ln in lineas
            ],

            "bars": [],
            "steps": [],
            "cost": 0,
            "margin": 0,
            "total_iva": 0,
        })

        return datos
    
    @staticmethod
    def crear_pedido(datos_pedido: dict, detalles: list[dict]) -> dict:
        """
        Crea un pedido completo.

        El consecutivo se obtiene desde ConsecutivoRepository.
        La cabecera y los detalles se guardan en una sola transacción.
        """

        # Validar antes de abrir la transacción.
        PedidosService._validar_cabecera(datos_pedido)
        PedidosService._validar_detalles(detalles)

        # Copiar los datos para no modificar los recibidos.
        cabecera = datos_pedido.copy()
        lista_detalles = [detalle.copy() for detalle in detalles]

        cabecera.setdefault("lote_interno", None)
        cabecera.setdefault("trm", 0)

        for detalle in lista_detalles:
            detalle.setdefault("precio_us", 0)
            detalle.setdefault("localizacion", None)
            detalle.setdefault("numero_lote", None)

        # Abrir la transacción.
        with Conexion.transaccion() as connection:

            # 1. Número temporal para las pruebas.
            numero_pedido = 8888

            cabecera["numero_pedido"] = numero_pedido

            # 2. Repositorio de cabecera.
            # Aquí debes utilizar tu PedidoRepository,
            # que inserta en pddos_prvdor.

            # 3. Repositorio de detalles.
            detalle_repo = NuevoPedidoRepository(connection)

            # 4. Insertar cada producto.
            for detalle in lista_detalles:

                detalle["numero_pedido"] = numero_pedido

                filas = detalle_repo.insertar_detalle_pedido(detalle)

                if filas != 1:
                    raise RuntimeError(
                        f"No fue posible insertar el PLU "
                        f"{detalle['codigo_plu']}."
                    )

        # Si el bloque terminó correctamente, SQLAlchemy hizo COMMIT.
        return {
            "exito": True,
            "mensaje": "Pedido creado correctamente.",
            "numero_pedido": numero_pedido,
            "total_productos": len(lista_detalles)
        }

    @staticmethod
    def _validar_cabecera(datos: dict) -> None:

        campos_obligatorios = [
            "codigo_proveedor",
            "fecha_pedido",
            "fecha_pactada",
            "tipo_pedido",
            "bodega_destino"
        ]

        for campo in campos_obligatorios:
            if campo not in datos or datos[campo] is None:
                raise ValueError(f"El campo {campo} es obligatorio.")

    @staticmethod
    def _validar_detalles(detalles: list[dict]) -> None:

        if not detalles:
            raise ValueError(
                "El pedido debe contener al menos un producto."
            )

        combinaciones = set()

        for detalle in detalles:

            for campo in (
                "codigo_plu",
                "cantidad_pedida",
                "nivel",
                "precio"
            ):
                if campo not in detalle or detalle[campo] is None:
                    raise ValueError(
                        f"Falta el campo {campo} en un producto."
                    )

            try:
                cantidad = float(detalle["cantidad_pedida"])
                float(detalle["precio"])
                float(detalle.get("precio_us", 0))
                clave = (
                    int(detalle["codigo_plu"]),
                    int(detalle["nivel"])
                )
            except (TypeError, ValueError):
                raise ValueError(
                    "El PLU, nivel, cantidad y precios deben ser válidos."
                )

            if cantidad <= 0:
                raise ValueError(
                    f"La cantidad del PLU {clave[0]} debe ser mayor que cero."
                )

            if clave in combinaciones:
                raise ValueError(
                    f"El PLU {clave[0]} está repetido "
                    f"con el nivel de limpieza {clave[1]}."
                )

            combinaciones.add(clave)
