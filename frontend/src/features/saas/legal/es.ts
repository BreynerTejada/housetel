import type { LegalTexts } from './types'

/** Documentos legales en español (versión de referencia: prevalece sobre la traducción al inglés). */
export const es: LegalTexts = {
  terminos: {
    title: 'Términos y condiciones',
    lead: 'Las reglas de uso de Housetel para los hoteles que lo contratan y para los huéspedes que reservan a través de él.',
    summary: [
      'Housetel es un software para hoteles y un marketplace de reservas: el contrato de hospedaje es siempre entre el huésped y el hotel.',
      'El hotel fija sus precios, impuestos, políticas de cancelación y condiciones, y responde por cumplir la ley colombiana (RNT, DIAN, TRA, SIRE y Habeas Data).',
      'Los planes son mensuales o anuales, sin permanencia; las reservas del marketplace pagan una comisión sobre el alojamiento.',
      'Los datos personales se tratan según la {privacy} y el {dpa}.',
    ],
    sections: [
      {
        id: 'alcance',
        title: '1. Quiénes somos y a quién aplican',
        body: [
          'Housetel («Housetel», «nosotros») opera una plataforma en la nube que incluye un sistema de gestión hotelera (PMS), un motor de reservas para el sitio web de cada hotel, conexiones con canales de venta y un marketplace de alojamientos en Colombia.',
          'Estos términos aplican a: (a) los hoteles, hostales y demás alojamientos que crean una cuenta y contratan un plan («el Hotel»), y a las personas que el Hotel invita a usar la plataforma; y (b) las personas que buscan, reservan o gestionan una reserva en el marketplace, en el motor de reservas de un hotel o en el portal del huésped («el Huésped»).',
          'Al crear una cuenta, reservar o usar la plataforma aceptas estos términos. Si actúas en nombre de un hotel, declaras que tienes facultades para obligarlo.',
        ],
      },
      {
        id: 'cuentas',
        title: '2. Cuentas y acceso',
        body: [
          'El Hotel entrega información veraz (razón social, NIT, datos de contacto y del establecimiento) y la mantiene actualizada.',
          {
            list: [
              'Cada usuario es personal: no compartas tu contraseña. El Hotel responde por las acciones de los usuarios que invita y por los permisos que les asigna.',
              'Avísanos de inmediato a {email} si sospechas un acceso no autorizado.',
              'Podemos pedir verificar el correo o la identidad del titular de la cuenta antes de activar funciones sensibles (pagos en línea, facturación electrónica).',
            ],
          },
        ],
      },
      {
        id: 'planes',
        title: '3. Planes, prueba gratuita y pagos del Hotel',
        body: [
          'Los planes, sus precios en pesos colombianos y lo que incluyen se publican en la plataforma. Todos los planes incluyen el PMS, el motor de reservas, el check-in online y el portal del huésped.',
          {
            list: [
              'Las cuentas nuevas tienen una prueba gratuita de 14 días. Al terminar, el plan se cobra por mes o por año por anticipado con el medio de pago registrado.',
              'No hay permanencia mínima: el Hotel puede cambiar de plan o cancelar en cualquier momento; la cancelación aplica al final del periodo pagado.',
              'Si un cobro falla, avisamos y reintentamos. Después del periodo de gracia, la cuenta puede quedar suspendida (solo lectura del plan y la facturación) hasta que se pague.',
              'Las reservas originadas en el marketplace de Housetel pagan una comisión sobre el valor del alojamiento sin impuestos, que se liquida mensualmente. Las cancelaciones sin penalidad reversan la comisión.',
              'Housetel expide la factura electrónica de sus servicios al Hotel.',
            ],
          },
        ],
      },
      {
        id: 'reservas',
        title: '4. Reservas de los huéspedes',
        body: [
          'En el marketplace y en el motor de reservas, Housetel actúa como intermediario tecnológico: muestra la oferta del Hotel y transmite la reserva. El contrato de hospedaje, la prestación del servicio y la factura del alojamiento son del Hotel.',
          {
            list: [
              'Antes de confirmar ves el precio total con impuestos, lo que pagas ahora y en el hotel, y la política de cancelación de tu tarifa. Esas condiciones las fija el Hotel.',
              'Los pagos en línea se procesan en la pasarela del Hotel (por ejemplo, Wompi). Housetel no almacena los datos completos de tu tarjeta.',
              'Cuando el hotel no tiene pagos en línea activos, la reserva se paga en el hotel.',
              'La exención de IVA del alojamiento para extranjeros no residentes se aplica según la normativa tributaria vigente; el Hotel puede verificar tu documento y tu sello de ingreso al llegar.',
              'Los cambios y cancelaciones se hacen desde el portal del huésped o con el Hotel, dentro de la política de tu tarifa.',
            ],
          },
          'Tus derechos como consumidor (Ley 1480 de 2011) se mantienen: estos términos no limitan lo que la ley no permite limitar.',
        ],
      },
      {
        id: 'hotel',
        title: '5. Obligaciones del Hotel',
        body: [
          {
            list: [
              'Mantener vigente su Registro Nacional de Turismo (RNT) y cumplir la regulación turística.',
              'Expedir las facturas electrónicas a sus huéspedes ante la DIAN, registrar la Tarjeta de Registro Alojamiento (TRA) y reportar a Migración Colombia (SIRE) los movimientos de extranjeros, directamente o con las herramientas de la plataforma en modo real.',
              'Cumplir la Ley 1581 de 2012 como responsable de los datos de sus huéspedes, obtener sus autorizaciones y atender sus solicitudes.',
              'Prevenir la explotación sexual comercial de niños, niñas y adolescentes (Ley 679 de 2001 y Ley 1336 de 2009) y verificar la identidad y el parentesco de los menores que se hospedan.',
              'Publicar información veraz (fotos, servicios, precios, disponibilidad y políticas) y respetar las reservas confirmadas.',
            ],
          },
        ],
      },
      {
        id: 'uso',
        title: '6. Uso aceptable',
        body: [
          'No está permitido usar Housetel para actividades ilícitas; intentar acceder a cuentas o datos ajenos; vulnerar o probar la seguridad sin autorización escrita; extraer datos de forma masiva o automatizada; publicar contenido engañoso, ofensivo o que infrinja derechos de terceros; ni revender el servicio sin un acuerdo con Housetel.',
        ],
      },
      {
        id: 'integraciones',
        title: '7. Integraciones y modo simulado',
        body: [
          'La plataforma se conecta con terceros: pasarelas de pago, proveedores tecnológicos de facturación electrónica, el servicio TRA de MinCIT, Migración Colombia, WhatsApp Business (Meta), channel managers y proveedores de inteligencia artificial. Esas conexiones dependen de los términos de cada tercero y de las credenciales del Hotel.',
          {
            note: 'En modo simulado nada se cobra, se factura, se reporta ni se envía de verdad: sirve para aprender y probar. El Hotel activa el modo real de cada integración cuando la configura, y es responsable de revisar que funcione.',
          },
        ],
      },
      {
        id: 'ia',
        title: '8. Funciones de inteligencia artificial',
        body: [
          'El copiloto, el chatbot, los borradores de mensajes, el onboarding asistido y las recomendaciones de precio usan modelos de inteligencia artificial. Sus respuestas pueden contener errores: las acciones que cambian datos siempre piden confirmación, y el Hotel revisa precios y mensajes antes de aplicarlos o enviarlos.',
        ],
      },
      {
        id: 'soporte',
        title: '9. Disponibilidad y soporte',
        body: [
          'Hacemos esfuerzos razonables para que la plataforma esté disponible y respaldada, y avisamos con anticipación los mantenimientos programados. El soporte se presta por {email} y por WhatsApp {whatsapp}.',
        ],
      },
      {
        id: 'datos',
        title: '10. Datos personales',
        body: [
          'Housetel trata los datos personales según su {privacy}. Respecto de los datos de los huéspedes que el Hotel registra en la plataforma, el Hotel es el responsable del tratamiento y Housetel actúa como encargado, en los términos del {dpa}, que forma parte de estos términos.',
        ],
      },
      {
        id: 'propiedad',
        title: '11. Propiedad intelectual',
        body: [
          'El software, la marca y los diseños de Housetel son de Housetel. El Hotel conserva la propiedad de sus datos y de sus contenidos (fotos, textos y logotipos) y nos autoriza a usarlos para prestar el servicio, incluida su publicación en el marketplace y en el motor de reservas mientras esté activo.',
        ],
      },
      {
        id: 'responsabilidad',
        title: '12. Responsabilidad',
        body: [
          'Housetel no responde por las decisiones comerciales del Hotel, por la prestación del servicio de alojamiento, por fallas de terceros (pasarelas, autoridades, canales o proveedores de internet) ni por fuerza mayor. Frente al Hotel, la responsabilidad total de Housetel se limita a lo pagado por el servicio en los doce meses anteriores al hecho, salvo dolo o culpa grave.',
        ],
      },
      {
        id: 'terminacion',
        title: '13. Terminación',
        body: [
          'El Hotel puede cerrar su cuenta en cualquier momento. Housetel puede suspender o terminar el servicio por mora o por incumplimiento grave de estos términos, avisando antes cuando sea posible. Tras la terminación, el Hotel puede exportar sus datos durante 30 días; después se suprimen de forma segura, salvo lo que la ley obliga a conservar.',
        ],
      },
      {
        id: 'cambios',
        title: '14. Cambios',
        body: [
          'Podemos actualizar estos términos. Los cambios sustanciales se avisan con al menos 15 días de anticipación por correo o dentro de la plataforma; seguir usándola después de esa fecha implica aceptarlos.',
        ],
      },
      {
        id: 'ley',
        title: '15. Ley aplicable',
        body: [
          'Estos términos se rigen por las leyes de la República de Colombia. Las controversias se resuelven ante los jueces colombianos competentes, sin perjuicio de los mecanismos de protección al consumidor ante la Superintendencia de Industria y Comercio.',
        ],
      },
      {
        id: 'contacto',
        title: '16. Contacto',
        body: ['Escríbenos a {email} o por WhatsApp {whatsapp}.'],
      },
    ],
  },

  privacidad: {
    title: 'Política de tratamiento de datos personales',
    lead: 'Cómo Housetel recoge, usa, protege y suprime datos personales, y cómo ejerces tus derechos (Ley 1581 de 2012 y Decreto 1377 de 2013, compilado en el Decreto 1074 de 2015).',
    summary: [
      'Usamos tus datos para gestionar reservas, estadías y pagos, y para cumplir las obligaciones legales de los hoteles (DIAN, TRA y SIRE).',
      'Los datos de los huéspedes que registra cada hotel son del hotel (responsable); Housetel los trata por su encargo.',
      'Las fotos de documentos y las firmas del check-in online se borran solas 180 días después de la salida, salvo que el hotel defina otro plazo.',
      'Puedes conocer, actualizar, rectificar y suprimir tus datos, o revocar tu autorización, escribiendo a {email}.',
    ],
    sections: [
      {
        id: 'responsable',
        title: '1. Responsable y encargado',
        body: [
          'Housetel es responsable del tratamiento de los datos de: (a) las personas que usan la plataforma en nombre de un hotel (usuarios); (b) los huéspedes que buscan y reservan en el marketplace, en lo relativo a la intermediación; y (c) quienes nos contactan o visitan nuestros sitios.',
          'Respecto de los datos de los huéspedes, acompañantes y contactos que cada hotel registra en su PMS, en su motor de reservas o en el check-in online, el responsable es el hotel y Housetel actúa como encargado, según el {dpa}.',
          'Canal de atención: {email}.',
        ],
      },
      {
        id: 'datos',
        title: '2. Datos que tratamos',
        body: [
          {
            list: [
              'Identificación: nombres, apellidos, tipo y número de documento, nacionalidad, país y ciudad de residencia, fecha de nacimiento.',
              'Contacto: correo electrónico, teléfono y WhatsApp.',
              'Reserva y estadía: fechas, habitación, acompañantes, hora de llegada, solicitudes, consumos, pagos y facturas.',
              'Datos que exige la ley al hotel: procedencia, destino y motivo del viaje (TRA y SIRE).',
              'Check-in online: foto del documento de identidad, firma y evidencia de la aceptación (fecha, dirección IP y navegador).',
              'Pagos: referencia y estado de la transacción. Los datos completos de la tarjeta los procesa la pasarela; Housetel no los almacena.',
              'Conversaciones por correo, WhatsApp y el chat del hotel.',
              'Usuarios: nombre, correo, rol, idioma y registro de actividad (auditoría).',
              'Datos técnicos: dirección IP, navegador y cookies necesarias para la sesión y la seguridad.',
            ],
          },
        ],
      },
      {
        id: 'sensibles',
        title: '3. Datos sensibles y de niños, niñas y adolescentes',
        body: [
          'No pedimos datos sensibles. Responder preguntas sobre datos sensibles, si alguna vez se hicieran, es facultativo. La foto del documento y la firma se guardan en un almacenamiento privado, sin enlaces públicos.',
          'Los datos de menores de edad se tratan solo cuando la ley lo exige para el registro hotelero, los entrega su representante legal y se respeta su interés superior y sus derechos fundamentales.',
        ],
      },
      {
        id: 'finalidades',
        title: '4. Para qué usamos los datos',
        body: [
          {
            list: [
              'Gestionar reservas, pagos, reembolsos, check-in, estadías y check-out.',
              'Cumplir obligaciones legales de los hoteles: factura electrónica (DIAN), Tarjeta de Registro Alojamiento (TRA, MinCIT), reporte de extranjeros (SIRE, Migración Colombia) y prevención de la explotación sexual comercial de niños, niñas y adolescentes.',
              'Enviar mensajes de servicio: confirmaciones, links de pago, check-in online y comunicaciones de la estadía.',
              'Prestar soporte, garantizar la seguridad, prevenir fraudes y mantener la auditoría de cambios.',
              'Elaborar estadísticas agregadas y mejorar el servicio.',
              'Enviar ofertas y novedades solo si lo autorizas por separado; puedes retirar esa autorización en cualquier momento.',
            ],
          },
        ],
      },
      {
        id: 'ia',
        title: '5. Inteligencia artificial',
        body: [
          'Algunas funciones que el hotel activa (resumen del día, borradores de respuesta, chatbot, explicaciones de precios) envían a proveedores de inteligencia artificial, como Google (Gemini) o Anthropic (Claude), solo los datos necesarios para responder. Esos proveedores actúan como encargados y no deben usar los datos para fines propios.',
        ],
      },
      {
        id: 'derechos',
        title: '6. Tus derechos',
        body: [
          'Como titular puedes (artículo 8 de la Ley 1581 de 2012):',
          {
            list: [
              'Conocer, actualizar y rectificar tus datos.',
              'Pedir prueba de la autorización que otorgaste.',
              'Ser informado sobre el uso que se da a tus datos.',
              'Presentar quejas ante la Superintendencia de Industria y Comercio (SIC), después de agotar el trámite ante el responsable.',
              'Revocar la autorización o pedir la supresión de tus datos cuando no exista un deber legal o contractual de conservarlos.',
              'Acceder gratuitamente a tus datos.',
            ],
          },
        ],
      },
      {
        id: 'procedimiento',
        title: '7. Consultas y reclamos',
        body: [
          'Envía tu solicitud a {email} con tu nombre, documento, datos de contacto, la descripción de lo que pides y, si aplica, los documentos de soporte.',
          {
            list: [
              'Consultas: se responden en máximo 10 días hábiles; si no es posible, te informamos el motivo y la nueva fecha, que no superará 5 días hábiles más.',
              'Reclamos (corrección, actualización, supresión o incumplimiento): se responden en máximo 15 días hábiles, prorrogables hasta 8 días hábiles más con aviso. Si el reclamo está incompleto, te pedimos completarlo dentro de los 5 días siguientes; si pasan 2 meses sin respuesta, se entiende desistido.',
              'Mientras se resuelve, el dato queda marcado como «reclamo en trámite».',
              'Si la solicitud es sobre datos que un hotel registró (Housetel como encargado), la trasladamos al hotel y lo apoyamos para responder a tiempo.',
            ],
          },
        ],
      },
      {
        id: 'transferencias',
        title: '8. Transmisiones y transferencias',
        body: [
          'Para prestar el servicio compartimos datos con proveedores que actúan como encargados: infraestructura en la nube, correo transaccional, WhatsApp Business (Meta), pasarelas de pago, proveedores tecnológicos de facturación electrónica, channel managers y proveedores de inteligencia artificial. Algunos están fuera de Colombia; exigimos niveles adecuados de protección conforme al artículo 26 de la Ley 1581 de 2012. También entregamos datos a las autoridades cuando la ley lo exige.',
        ],
      },
      {
        id: 'seguridad',
        title: '9. Seguridad',
        body: [
          'Aplicamos medidas técnicas y administrativas razonables: cifrado en tránsito, credenciales de integraciones cifradas, almacenamiento privado para documentos y firmas, acceso por roles y por hotel, auditoría de acciones y copias de respaldo.',
        ],
      },
      {
        id: 'conservacion',
        title: '10. Conservación y supresión',
        body: [
          'Conservamos los datos mientras sean necesarios para las finalidades descritas y durante los plazos que exigen las normas contables, tributarias y de registro hotelero (por ejemplo, las facturas electrónicas).',
          {
            note: 'Las fotos de los documentos de identidad y las firmas del check-in online se borran automáticamente 180 días después de la salida del huésped. Cada hotel puede configurar otro plazo, y cada borrado queda registrado en la auditoría.',
          },
          'Cuando no existe un deber de conservar un dato, puedes pedir su supresión o la anonimización de tu perfil.',
        ],
      },
      {
        id: 'cookies',
        title: '11. Cookies',
        body: [
          'Usamos solo cookies y almacenamiento local necesarios: sesión, protección contra falsificación de peticiones (CSRF), idioma, tema y la conversación del chat. No usamos cookies publicitarias ni de seguimiento de terceros.',
        ],
      },
      {
        id: 'vigencia',
        title: '12. Vigencia y cambios',
        body: [
          'Esta política rige desde el 28 de septiembre de 2026. Las bases de datos se mantienen mientras duren las finalidades del tratamiento. Si la cambiamos de forma sustancial, lo avisaremos antes de aplicarla.',
        ],
      },
    ],
  },

  'encargo-datos': {
    title: 'Contrato de encargo del tratamiento de datos',
    lead: 'Las condiciones con las que Housetel trata, por cuenta de cada hotel, los datos de sus huéspedes (transmisión de datos entre responsable y encargado).',
    summary: [
      'El hotel es el responsable de los datos de sus huéspedes; Housetel es su encargado y solo los trata para prestar el servicio.',
      'Housetel protege los datos, avisa los incidentes de seguridad y ayuda al hotel a atender a los titulares.',
      'El hotel obtiene las autorizaciones; la plataforma incluye las casillas de consentimiento en el checkout y el check-in online.',
      'Al terminar, el hotel exporta sus datos durante 30 días y luego se suprimen, salvo lo que la ley obliga a conservar.',
    ],
    sections: [
      {
        id: 'objeto',
        title: '1. Partes y objeto',
        body: [
          'Este contrato se celebra entre el Hotel que crea una cuenta en Housetel («el Responsable») y Housetel («el Encargado»), y se acepta al registrarse o al contratar un plan. Regula la transmisión de datos personales de huéspedes, acompañantes, contactos y personal del Hotel que se registran en la plataforma, en los términos del artículo 25 del Decreto 1377 de 2013 (artículo 2.2.2.25.5.2 del Decreto 1074 de 2015).',
        ],
      },
      {
        id: 'roles',
        title: '2. Roles',
        body: [
          'El Responsable decide las finalidades del tratamiento, obtiene y conserva las autorizaciones, publica su política de tratamiento y atiende a los titulares. El Encargado trata los datos solo por cuenta del Responsable y según sus instrucciones, que se expresan en este contrato y en la configuración y el uso que el Hotel hace de la plataforma.',
        ],
      },
      {
        id: 'instrucciones',
        title: '3. Tratamiento autorizado',
        body: [
          'El Encargado trata los datos para prestar el servicio contratado: PMS, motor de reservas, conexión con canales, mensajería, pagos, facturación electrónica, reportes legales (TRA y SIRE), reportes y las funciones de inteligencia artificial que el Hotel active. No usa los datos para fines propios, salvo estadísticas agregadas y anónimas y lo estrictamente necesario para la seguridad y la facturación del servicio.',
        ],
      },
      {
        id: 'encargado',
        title: '4. Obligaciones del Encargado',
        body: [
          'Además de los deberes del artículo 18 de la Ley 1581 de 2012, el Encargado se obliga a:',
          {
            list: [
              'Tratar los datos con confidencialidad y exigirla a su personal y a sus sub-encargados.',
              'Aplicar las medidas de seguridad descritas en este contrato.',
              'Actualizar, rectificar o suprimir los datos cuando el Responsable lo indique o lo haga desde la plataforma.',
              'Trasladar al Responsable, dentro de los 5 días hábiles siguientes, las consultas y reclamos de titulares que reciba directamente, y registrar la leyenda «reclamo en trámite» cuando corresponda.',
              'Permitir el acceso a los datos solo a las personas que lo necesitan para prestar el servicio.',
            ],
          },
        ],
      },
      {
        id: 'responsable',
        title: '5. Obligaciones del Responsable',
        body: [
          {
            list: [
              'Obtener la autorización previa, expresa e informada de los titulares. La plataforma incluye casillas de autorización en el checkout y en el check-in online que enlazan a la {privacy}.',
              'Informar a los titulares la finalidad del tratamiento y sus derechos.',
              'Registrar solo datos obtenidos lícitamente y necesarios para la estadía y las obligaciones legales.',
              'Administrar los usuarios y permisos de su equipo.',
              'Definir el plazo de conservación de los documentos de identidad y las firmas (por defecto 180 días después de la salida).',
            ],
          },
        ],
      },
      {
        id: 'seguridad',
        title: '6. Medidas de seguridad',
        body: [
          {
            list: [
              'Cifrado de las comunicaciones (TLS) y de las credenciales de las integraciones.',
              'Almacenamiento privado para documentos y firmas, sin enlaces públicos; solo se leen con una sesión autorizada del Hotel.',
              'Control de acceso por rol y por propiedad, y registro de auditoría de las acciones.',
              'Copias de respaldo periódicas y restauración probada.',
              'Registros técnicos sin datos personales en claro.',
            ],
          },
        ],
      },
      {
        id: 'subencargados',
        title: '7. Sub-encargados',
        body: [
          'El Responsable autoriza de forma general al Encargado a apoyarse en proveedores que tratan datos por su cuenta, con obligaciones equivalentes a las de este contrato: infraestructura en la nube, correo transaccional, WhatsApp Business (Meta), pasarelas de pago (Wompi), proveedores tecnológicos de facturación electrónica (Factus), channel managers (Channex) y proveedores de inteligencia artificial (Google y Anthropic). El Encargado mantiene la lista actualizada y avisa los cambios relevantes.',
        ],
      },
      {
        id: 'internacional',
        title: '8. Transmisión internacional',
        body: [
          'Algunos sub-encargados tratan datos fuera de Colombia. El Encargado garantiza que ofrecen niveles adecuados de protección, conforme al artículo 26 de la Ley 1581 de 2012 y a las instrucciones de la Superintendencia de Industria y Comercio.',
        ],
      },
      {
        id: 'incidentes',
        title: '9. Incidentes de seguridad',
        body: [
          'El Encargado notifica al Responsable cualquier incidente que afecte datos personales sin demora injustificada, y a más tardar dentro de las 72 horas siguientes a conocerlo, con la información disponible y las medidas tomadas. Colabora para que el Responsable lo reporte a la Superintendencia de Industria y Comercio dentro de los 15 días hábiles siguientes a su detección y, si procede, lo informe a los titulares.',
        ],
      },
      {
        id: 'titulares',
        title: '10. Apoyo con los derechos de los titulares',
        body: [
          'La plataforma permite consultar, exportar, rectificar y anonimizar los datos de un huésped. El Encargado apoya al Responsable para responder consultas y reclamos dentro de los plazos legales.',
        ],
      },
      {
        id: 'conservacion',
        title: '11. Conservación, devolución y supresión',
        body: [
          'Durante el contrato, las fotos de documentos y las firmas se borran automáticamente según el plazo que configure el Responsable (por defecto 180 días después de la salida; 0 significa conservarlas, bajo responsabilidad del Hotel). Al terminar el contrato, el Responsable puede exportar sus datos durante 30 días; después, el Encargado los suprime de forma segura, salvo los que deba conservar por mandato legal.',
        ],
      },
      {
        id: 'verificacion',
        title: '12. Verificación',
        body: [
          'El Responsable puede pedir información razonable sobre las medidas de seguridad y el cumplimiento de este contrato. El Encargado responde en un plazo razonable, sin comprometer la seguridad de otros clientes.',
        ],
      },
      {
        id: 'vigencia',
        title: '13. Vigencia y ley aplicable',
        body: [
          'Este contrato rige mientras el Hotel use la plataforma y hasta que se devuelvan o supriman los datos; la confidencialidad se mantiene después. Se rige por las leyes de Colombia. Preguntas: {email}.',
        ],
      },
    ],
  },
}
