    import ssl
    from paho import mqtt
    import paho.mqtt.client as paho
    import paho.mqtt.publish as publish
    import paho.mqtt.subscribe as subscribe
    from paho import mqtt
    from time import sleep
    import ast

    from rich import print

    from rich import print

    class HiveMQTT:

        connected = False

        def connect_receiver():
            try:
                # use TLS for secure connection with HiveMQ Cloud
                sslSettings = ssl.SSLContext(mqtt.client.ssl.PROTOCOL_TLS)

                 # put in your cluster credentials and hostname
                auth = {'username': "trappyscope", 'password': "cr_in_trappy"}
                subscribe.callback(HiveMQTT.print_msg, "#", 
                                hostname="d093a1f309db470597759456d1eeefd4.s1.eu.hivemq.cloud",
                                port=8883, auth=auth,
                                tls=sslSettings, protocol=paho.MQTTv31)
                HiveMQTT.connected = True
            except:
                HiveMQTT.connected = False

        def send(topic, message):
            return
            # use TLS for secure connection with HiveMQ Cloud
            sslSettings = ssl.SSLContext(mqtt.client.ssl.PROTOCOL_TLS)
        
            msgs = [{'topic': topic, 'payload': str(message)}]

            # put in your cluster credentials and hostname
            auth = {'username': "trappyscope", 'password': "cr_in_trappy"}
            publish.multiple(msgs, hostname="d093a1f309db470597759456d1eeefd4.s1.eu.hivemq.cloud", port=8883, auth=auth,
                             tls=sslSettings, protocol=paho.MQTTv31)
            print("HiveMQTT sent >>", message)



            

           