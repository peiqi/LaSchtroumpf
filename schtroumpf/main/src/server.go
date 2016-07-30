package main

import (
	. "./common"
	"log"
	"net"
	"fmt"
	"os"
)

const (
	MAXCLIENTS = 30
)

type ClientTable map[net.Conn]*Client

type Counter chan int
type Server struct {
	listener net.Listener
	clients  ClientTable
	coming   Message
	pending  chan net.Conn
	//	outing  Message
	counter Counter
}

func CreateServer() *Server {
	server := &Server{
		counter: make(Counter),
		coming:  make(Message),
		pending: make(chan net.Conn),
		clients: make(ClientTable)}

	server.listen()
	return server
}

func (self *Server) join(conn net.Conn) {
	client := CreateClient(conn)
	client.SetName()
	self.clients[conn] = client

	go func() {
		for {
			msg := <-client.Incoming
			log.Printf("Got message: %s from client %s\n", msg, client.Name)

			self.coming <- fmt.Sprintf("%s says: %s", client.Name, msg)
		}
	}()
}
func (self *Server) listen() {
	go func() {
		for {
			select {
			case message := <-self.pending:
				self.join(message)
			case mess := <-self.coming:
				self.broadcast(mess)
			}

		}
	}()
}

func (self *Server) broadcast(message string) {
	for _, client := range self.clients {
		client.Outing <- message
	}
}
func (self *Server) Start(connString string) {
	self.listener, _ = net.Listen("tcp", connString)

	for {
		conn, _ := self.listener.Accept()
		self.pending <- conn
		log.Printf("a new connnection %s is established", conn)
	}
}

func main() {
	if len(os.Args) != 2 {
		fmt.Printf("Usage: %s \n", os.Args[0])
		os.Exit(-1)
	}

	server := CreateServer()
	fmt.Printf("Running on %s\n", os.Args[1])
	server.Start(os.Args[1])

}
