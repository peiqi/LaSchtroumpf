package main

//package chat

import (
	"bufio"
	"log"
	"net"
	"os"
)

type Message chan string

type Client struct {
	Name     string
	Incoming Message
	Outing   Message
	reader   *bufio.Reader
	writer   *bufio.Writer
}

func CreateClient(conn net.Conn) *Client {
	read := bufio.NewReader(conn)
	write := bufio.NewWriter(conn)

	client := &Client{
		Incoming: make(Message),
		Outing:   make(Message),
		reader:   read,
		writer:   write,
	}
	client.Listen()
	return client
}

func (self *Client) Listen() {
	go self.Read()
	go self.Write()
}

func (self *Client) Read() {
	for {
		if line, _, err := self.reader.ReadLine(); err == nil {
			self.Incoming <- string(line)
		} else {
			log.Printf("Read error: %s \n", err)
			return
		}
	}
}

func (self *Client) Write() {
	for out := range self.Outing {
		if _, err := self.writer.WriteString(out + "\n"); err != nil {
			log.Printf("Write error: %s \n", err)
			return
		}
		if err := self.writer.Flush(); err != nil {

			log.Printf("Write Flush error: %s \n", err)
			return
		}
	}
}

func (self *Client) INcoming() string {
	return <-self.Incoming
}

func (self *Client) Outgoing(message string) {
	self.Outing <- message
}

func (self *Client) SetName() {
	self.Name = "dodo"
}

func main() {

	if len(os.Args) != 2 {
		log.Printf("error, Usage: %s is in the form of client ip:port \n", os.Args[0])
	}
	conn, err := net.Dial("tcp", os.Args[1])
	if err != nil {
		log.Fatal("test peiqi ", err)
	}
	defer conn.Close()
	out := bufio.NewWriter(os.Stdout)
	in := bufio.NewReader(os.Stdin)
	client := CreateClient(conn)
	go func() {
		for {
			out.WriteString(client.INcoming() + "\n")
		out.Flush()
}
	}()

	for {
		line, _, _ := in.ReadLine()
		client.Outgoing(string(line))
	}

}
