import type { LegalTexts } from './types'

/** Legal documents in English (translation: the Spanish version prevails). */
export const en: LegalTexts = {
  terminos: {
    title: 'Terms and conditions',
    lead: 'The rules for using Housetel, for the hotels that subscribe to it and for the guests who book through it.',
    summary: [
      'Housetel is software for hotels and a booking marketplace: the accommodation contract is always between the guest and the hotel.',
      'Each hotel sets its prices, taxes, cancellation policies and conditions, and is responsible for complying with Colombian law (RNT, DIAN, TRA, SIRE and Habeas Data).',
      'Plans are monthly or yearly, with no lock-in; marketplace bookings pay a commission on the lodging amount.',
      'Personal data is processed under the {privacy} and the {dpa}.',
    ],
    sections: [
      {
        id: 'alcance',
        title: '1. Who we are and who these terms apply to',
        body: [
          'Housetel ("Housetel", "we") runs a cloud platform that includes a property management system (PMS), a booking engine for each hotel\'s website, connections to sales channels and an accommodation marketplace in Colombia.',
          'These terms apply to: (a) the hotels, hostels and other properties that create an account and subscribe to a plan ("the Hotel"), and the people the Hotel invites to use the platform; and (b) the people who search, book or manage a booking on the marketplace, on a hotel\'s booking engine or on the guest portal ("the Guest").',
          'By creating an account, booking or using the platform you accept these terms. If you act on behalf of a hotel, you confirm you are authorized to bind it.',
        ],
      },
      {
        id: 'cuentas',
        title: '2. Accounts and access',
        body: [
          'The Hotel provides accurate information (legal name, tax ID (NIT), contact and property details) and keeps it up to date.',
          {
            list: [
              'Each user account is personal: do not share your password. The Hotel is responsible for what the users it invites do and for the permissions it grants them.',
              'Tell us right away at {email} if you suspect unauthorized access.',
              'We may ask to verify the e-mail or the identity of the account holder before enabling sensitive features (online payments, e-invoicing).',
            ],
          },
        ],
      },
      {
        id: 'planes',
        title: '3. Plans, free trial and Hotel payments',
        body: [
          'Plans, their prices in Colombian pesos and what they include are published on the platform. Every plan includes the PMS, the booking engine, online check-in and the guest portal.',
          {
            list: [
              'New accounts get a 14-day free trial. After it ends, the plan is charged monthly or yearly in advance to the registered payment method.',
              'There is no minimum term: the Hotel can change plans or cancel at any time; cancellation takes effect at the end of the paid period.',
              'If a charge fails we notify you and retry. After the grace period the account may be suspended (read-only plan and billing) until it is paid.',
              'Bookings that come from the Housetel marketplace pay a commission on the lodging amount before taxes, settled monthly. Cancellations without a fee reverse the commission.',
              'Housetel issues the e-invoice for its services to the Hotel.',
            ],
          },
        ],
      },
      {
        id: 'reservas',
        title: '4. Guest bookings',
        body: [
          'On the marketplace and the booking engine, Housetel acts as a technology intermediary: it shows the Hotel\'s offer and passes the booking on. The accommodation contract, the service and the invoice for the stay belong to the Hotel.',
          {
            list: [
              'Before confirming you see the total price with taxes, what you pay now and at the hotel, and your rate\'s cancellation policy. The Hotel sets those conditions.',
              'Online payments are processed on the Hotel\'s gateway (for example, Wompi). Housetel never stores your full card details.',
              'When the hotel has no online payments enabled, the booking is paid at the hotel.',
              'The lodging VAT exemption for foreign non-residents applies under current tax rules; the Hotel may check your ID and entry stamp on arrival.',
              'Changes and cancellations are made on the guest portal or with the Hotel, within your rate\'s policy.',
            ],
          },
          'Your consumer rights (Law 1480 of 2011) remain: these terms do not limit anything the law does not allow to be limited.',
        ],
      },
      {
        id: 'hotel',
        title: '5. Hotel obligations',
        body: [
          {
            list: [
              'Keep its National Tourism Registry (RNT) current and comply with tourism regulations.',
              'Issue e-invoices to its guests before the DIAN, file the lodging registration card (TRA) and report foreigners\' movements to Migración Colombia (SIRE), directly or with the platform\'s tools in real mode.',
              'Comply with Law 1581 of 2012 as the controller of its guests\' data, obtain their consent and answer their requests.',
              'Prevent the commercial sexual exploitation of children and adolescents (Law 679 of 2001 and Law 1336 of 2009) and verify the identity and relationship of minors who stay.',
              'Publish accurate information (photos, amenities, prices, availability and policies) and honor confirmed bookings.',
            ],
          },
        ],
      },
      {
        id: 'uso',
        title: '6. Acceptable use',
        body: [
          'You may not use Housetel for unlawful activities; try to access other people\'s accounts or data; breach or test security without written permission; extract data massively or automatically; publish misleading, offensive or infringing content; or resell the service without an agreement with Housetel.',
        ],
      },
      {
        id: 'integraciones',
        title: '7. Integrations and simulated mode',
        body: [
          'The platform connects with third parties: payment gateways, e-invoicing technology providers, MinCIT\'s TRA service, Migración Colombia, WhatsApp Business (Meta), channel managers and artificial intelligence providers. Those connections depend on each third party\'s terms and on the Hotel\'s credentials.',
          {
            note: 'In simulated mode nothing is actually charged, invoiced, reported or sent: it is for learning and testing. The Hotel switches each integration to real mode when it configures it, and is responsible for checking it works.',
          },
        ],
      },
      {
        id: 'ia',
        title: '8. Artificial intelligence features',
        body: [
          'The copilot, the chatbot, message drafts, assisted onboarding and price recommendations use artificial intelligence models. Their answers may contain mistakes: actions that change data always ask for confirmation, and the Hotel reviews prices and messages before applying or sending them.',
        ],
      },
      {
        id: 'soporte',
        title: '9. Availability and support',
        body: [
          'We make reasonable efforts to keep the platform available and backed up, and we announce scheduled maintenance in advance. Support is provided at {email} and on WhatsApp {whatsapp}.',
        ],
      },
      {
        id: 'datos',
        title: '10. Personal data',
        body: [
          'Housetel processes personal data under its {privacy}. For the guest data the Hotel records on the platform, the Hotel is the controller and Housetel acts as processor, under the {dpa}, which is part of these terms.',
        ],
      },
      {
        id: 'propiedad',
        title: '11. Intellectual property',
        body: [
          'Housetel\'s software, brand and designs belong to Housetel. The Hotel keeps ownership of its data and content (photos, texts and logos) and authorizes us to use them to provide the service, including publishing them on the marketplace and the booking engine while it is active.',
        ],
      },
      {
        id: 'responsabilidad',
        title: '12. Liability',
        body: [
          'Housetel is not liable for the Hotel\'s business decisions, for the accommodation service, for third-party failures (gateways, authorities, channels or internet providers) or for force majeure. Towards the Hotel, Housetel\'s total liability is limited to the amount paid for the service in the twelve months before the event, except in cases of willful misconduct or gross negligence.',
        ],
      },
      {
        id: 'terminacion',
        title: '13. Termination',
        body: [
          'The Hotel can close its account at any time. Housetel may suspend or terminate the service for non-payment or serious breach of these terms, with prior notice when possible. After termination the Hotel can export its data for 30 days; afterwards it is securely deleted, except what the law requires to be kept.',
        ],
      },
      {
        id: 'cambios',
        title: '14. Changes',
        body: [
          'We may update these terms. Substantial changes are announced at least 15 days in advance by e-mail or in the platform; continuing to use it after that date means you accept them.',
        ],
      },
      {
        id: 'ley',
        title: '15. Governing law',
        body: [
          'These terms are governed by the laws of the Republic of Colombia. Disputes are settled before the competent Colombian courts, without prejudice to consumer protection mechanisms before the Superintendence of Industry and Commerce (SIC).',
        ],
      },
      {
        id: 'contacto',
        title: '16. Contact',
        body: ['Write to us at {email} or on WhatsApp {whatsapp}.'],
      },
    ],
  },

  privacidad: {
    title: 'Personal data processing policy',
    lead: 'How Housetel collects, uses, protects and deletes personal data, and how you exercise your rights (Colombian Law 1581 of 2012 and Decree 1377 of 2013, compiled in Decree 1074 of 2015).',
    summary: [
      'We use your data to manage bookings, stays and payments, and to meet the hotels\' legal obligations (DIAN, TRA and SIRE).',
      'The guest data each hotel records belongs to that hotel (controller); Housetel processes it on the hotel\'s behalf.',
      'Document photos and online check-in signatures are deleted automatically 180 days after departure, unless the hotel sets another period.',
      'You can access, update, correct and delete your data, or withdraw your consent, by writing to {email}.',
    ],
    sections: [
      {
        id: 'responsable',
        title: '1. Controller and processor',
        body: [
          'Housetel is the controller of the data of: (a) the people who use the platform on behalf of a hotel (users); (b) the guests who search and book on the marketplace, regarding the intermediation; and (c) people who contact us or visit our sites.',
          'For the data of guests, companions and contacts that each hotel records in its PMS, its booking engine or online check-in, the hotel is the controller and Housetel acts as processor, under the {dpa}.',
          'Contact channel: {email}.',
        ],
      },
      {
        id: 'datos',
        title: '2. Data we process',
        body: [
          {
            list: [
              'Identification: first and last names, document type and number, nationality, country and city of residence, date of birth.',
              'Contact: e-mail, phone and WhatsApp.',
              'Booking and stay: dates, room, companions, arrival time, requests, charges, payments and invoices.',
              'Data the law requires hotels to collect: origin, destination and purpose of the trip (TRA and SIRE).',
              'Online check-in: a photo of the ID document, the signature and the proof of acceptance (date, IP address and browser).',
              'Payments: transaction reference and status. The full card details are handled by the gateway; Housetel does not store them.',
              'Conversations by e-mail, WhatsApp and the hotel\'s chat.',
              'Users: name, e-mail, role, language and activity log (audit).',
              'Technical data: IP address, browser and the cookies needed for the session and security.',
            ],
          },
        ],
      },
      {
        id: 'sensibles',
        title: '3. Sensitive data and children\'s data',
        body: [
          'We do not ask for sensitive data. Answering questions about sensitive data, should they ever be asked, is optional. ID photos and signatures are kept in private storage, with no public links.',
          'Minors\' data is processed only when the law requires it for the hotel registration, it is provided by their legal representative, and their best interest and fundamental rights are respected.',
        ],
      },
      {
        id: 'finalidades',
        title: '4. What we use the data for',
        body: [
          {
            list: [
              'Managing bookings, payments, refunds, check-in, stays and check-out.',
              'Meeting the hotels\' legal obligations: e-invoicing (DIAN), the lodging registration card (TRA, MinCIT), the foreigners report (SIRE, Migración Colombia) and the prevention of the commercial sexual exploitation of children and adolescents.',
              'Sending service messages: confirmations, payment links, online check-in and messages about the stay.',
              'Providing support, keeping the platform secure, preventing fraud and keeping the audit log of changes.',
              'Building aggregated statistics and improving the service.',
              'Sending offers and news only if you agree separately; you can withdraw that consent at any time.',
            ],
          },
        ],
      },
      {
        id: 'ia',
        title: '5. Artificial intelligence',
        body: [
          'Some features the hotel turns on (daily brief, reply drafts, chatbot, price explanations) send artificial intelligence providers such as Google (Gemini) or Anthropic (Claude) only the data needed to answer. Those providers act as processors and must not use the data for their own purposes.',
        ],
      },
      {
        id: 'derechos',
        title: '6. Your rights',
        body: [
          'As the data subject you can (article 8 of Law 1581 of 2012):',
          {
            list: [
              'Access, update and correct your data.',
              'Ask for proof of the consent you gave.',
              'Be informed about how your data is used.',
              'File complaints with the Superintendence of Industry and Commerce (SIC), after completing the process with the controller.',
              'Withdraw your consent or ask for your data to be deleted when there is no legal or contractual duty to keep it.',
              'Access your data free of charge.',
            ],
          },
        ],
      },
      {
        id: 'procedimiento',
        title: '7. Requests and complaints',
        body: [
          'Send your request to {email} with your name, ID, contact details, a description of what you are asking for and, if applicable, supporting documents.',
          {
            list: [
              'Requests for information are answered within 10 business days; if that is not possible, we tell you why and the new date, no more than 5 additional business days.',
              'Complaints (correction, update, deletion or breach) are answered within 15 business days, extendable by up to 8 business days with notice. If a complaint is incomplete we ask you to complete it within 5 days; after 2 months without an answer it is considered withdrawn.',
              'While it is being resolved, the data is flagged as "complaint in progress".',
              'If the request concerns data a hotel recorded (Housetel as processor), we forward it to the hotel and help it answer on time.',
            ],
          },
        ],
      },
      {
        id: 'transferencias',
        title: '8. Transmissions and transfers',
        body: [
          'To provide the service we share data with providers acting as processors: cloud infrastructure, transactional e-mail, WhatsApp Business (Meta), payment gateways, e-invoicing technology providers, channel managers and artificial intelligence providers. Some are outside Colombia; we require adequate levels of protection under article 26 of Law 1581 of 2012. We also hand data to the authorities when the law requires it.',
        ],
      },
      {
        id: 'seguridad',
        title: '9. Security',
        body: [
          'We apply reasonable technical and organizational measures: encryption in transit, encrypted integration credentials, private storage for documents and signatures, access by role and by hotel, an audit log of actions and backups.',
        ],
      },
      {
        id: 'conservacion',
        title: '10. Retention and deletion',
        body: [
          'We keep data while it is needed for the purposes above and for the periods required by accounting, tax and hotel registration rules (for example, e-invoices).',
          {
            note: 'Photos of ID documents and online check-in signatures are deleted automatically 180 days after the guest\'s departure. Each hotel can set a different period, and every deletion is recorded in the audit log.',
          },
          'When there is no duty to keep a piece of data, you can ask for it to be deleted or for your profile to be anonymized.',
        ],
      },
      {
        id: 'cookies',
        title: '11. Cookies',
        body: [
          'We only use the cookies and local storage that are needed: session, cross-site request forgery (CSRF) protection, language, theme and the chat conversation. We do not use advertising or third-party tracking cookies.',
        ],
      },
      {
        id: 'vigencia',
        title: '12. Effective date and changes',
        body: [
          'This policy is effective from September 28, 2026. The databases are kept for as long as the purposes of the processing last. If we change it substantially, we will announce it before it applies.',
        ],
      },
    ],
  },

  'encargo-datos': {
    title: 'Data processing agreement',
    lead: 'The terms under which Housetel processes each hotel\'s guest data on the hotel\'s behalf (transmission of data between controller and processor).',
    summary: [
      'The hotel is the controller of its guests\' data; Housetel is its processor and only uses the data to provide the service.',
      'Housetel protects the data, reports security incidents and helps the hotel answer data subjects.',
      'The hotel obtains the consents; the platform includes the consent checkboxes in the checkout and online check-in.',
      'When the contract ends, the hotel can export its data for 30 days; then it is deleted, except what the law requires to be kept.',
    ],
    sections: [
      {
        id: 'objeto',
        title: '1. Parties and purpose',
        body: [
          'This agreement is entered into between the Hotel that creates a Housetel account ("the Controller") and Housetel ("the Processor"), and is accepted when signing up or subscribing to a plan. It governs the transmission of personal data of guests, companions, contacts and Hotel staff recorded on the platform, under article 25 of Decree 1377 of 2013 (article 2.2.2.25.5.2 of Decree 1074 of 2015).',
        ],
      },
      {
        id: 'roles',
        title: '2. Roles',
        body: [
          'The Controller decides the purposes of the processing, obtains and keeps the consents, publishes its data policy and answers the data subjects. The Processor processes the data only on the Controller\'s behalf and following its instructions, which are set out in this agreement and in how the Hotel configures and uses the platform.',
        ],
      },
      {
        id: 'instrucciones',
        title: '3. Authorized processing',
        body: [
          'The Processor processes the data to provide the subscribed service: PMS, booking engine, channel connections, messaging, payments, e-invoicing, legal reports (TRA and SIRE), reports and the artificial intelligence features the Hotel turns on. It does not use the data for its own purposes, except for aggregated anonymous statistics and what is strictly needed for the security and billing of the service.',
        ],
      },
      {
        id: 'encargado',
        title: '4. Processor obligations',
        body: [
          'In addition to the duties of article 18 of Law 1581 of 2012, the Processor undertakes to:',
          {
            list: [
              'Keep the data confidential and require the same from its staff and sub-processors.',
              'Apply the security measures described in this agreement.',
              'Update, correct or delete data when the Controller instructs it or does so on the platform.',
              'Forward to the Controller, within 5 business days, the requests and complaints it receives directly from data subjects, and flag data as "complaint in progress" when applicable.',
              'Give access to the data only to the people who need it to provide the service.',
            ],
          },
        ],
      },
      {
        id: 'responsable',
        title: '5. Controller obligations',
        body: [
          {
            list: [
              'Obtain the prior, express and informed consent of data subjects. The platform includes consent checkboxes in the checkout and online check-in that link to the {privacy}.',
              'Inform data subjects about the purpose of the processing and their rights.',
              'Record only lawfully obtained data needed for the stay and the legal obligations.',
              'Manage the users and permissions of its team.',
              'Set the retention period for ID documents and signatures (180 days after departure by default).',
            ],
          },
        ],
      },
      {
        id: 'seguridad',
        title: '6. Security measures',
        body: [
          {
            list: [
              'Encryption of communications (TLS) and of integration credentials.',
              'Private storage for documents and signatures, with no public links; they are only read with an authorized Hotel session.',
              'Access control by role and by property, and an audit log of actions.',
              'Regular backups with tested restores.',
              'Technical logs without personal data in clear text.',
            ],
          },
        ],
      },
      {
        id: 'subencargados',
        title: '7. Sub-processors',
        body: [
          'The Controller gives the Processor general authorization to rely on providers that process data on its behalf, with obligations equivalent to this agreement: cloud infrastructure, transactional e-mail, WhatsApp Business (Meta), payment gateways (Wompi), e-invoicing technology providers (Factus), channel managers (Channex) and artificial intelligence providers (Google and Anthropic). The Processor keeps the list up to date and announces relevant changes.',
        ],
      },
      {
        id: 'internacional',
        title: '8. International transmission',
        body: [
          'Some sub-processors process data outside Colombia. The Processor ensures they offer adequate levels of protection, under article 26 of Law 1581 of 2012 and the instructions of the Superintendence of Industry and Commerce.',
        ],
      },
      {
        id: 'incidentes',
        title: '9. Security incidents',
        body: [
          'The Processor notifies the Controller of any incident affecting personal data without undue delay, and no later than 72 hours after becoming aware of it, with the information available and the measures taken. It helps the Controller report it to the Superintendence of Industry and Commerce within 15 business days of its detection and, where appropriate, inform the data subjects.',
        ],
      },
      {
        id: 'titulares',
        title: '10. Help with data subjects\' rights',
        body: [
          'The platform lets the Hotel look up, export, correct and anonymize a guest\'s data. The Processor helps the Controller answer requests and complaints within the legal deadlines.',
        ],
      },
      {
        id: 'conservacion',
        title: '11. Retention, return and deletion',
        body: [
          'During the agreement, document photos and signatures are deleted automatically after the period the Controller configures (180 days after departure by default; 0 means keeping them, under the Hotel\'s responsibility). When the agreement ends, the Controller can export its data for 30 days; then the Processor securely deletes it, except the data it must keep by law.',
        ],
      },
      {
        id: 'verificacion',
        title: '12. Verification',
        body: [
          'The Controller may ask for reasonable information about the security measures and compliance with this agreement. The Processor answers within a reasonable time, without compromising the security of other customers.',
        ],
      },
      {
        id: 'vigencia',
        title: '13. Term and governing law',
        body: [
          'This agreement applies while the Hotel uses the platform and until the data is returned or deleted; confidentiality survives it. It is governed by the laws of Colombia. Questions: {email}.',
        ],
      },
    ],
  },
}
